#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""S06 unified import-entry matrix compiler.

Turns one platform's real probe stream into named matrix cells and refuses to
call anything passed without same-source, same-run, same-binary evidence.

Rules enforced here, not in prose:

* every cell names the exact cases that must be present and passing;
* a stream declares the layer it actually exercised, and a module-level stream
  can never fill a cell that requires a real operating-system handoff;
* source SHA, run id, attempt, platform and probe binary digest must all match
  the run being compiled, and every bound file is hashed and sized;
* a target this run declares measurable but produced no evidence fails the run
  instead of quietly becoming "pending".
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile

LAYER_RANK = {"module": 1, "host": 2}
STATUSES = ("pass", "fail", "skip")


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path, problems, label):
    if not os.path.isfile(path):
        problems.append("%s: missing %s" % (label, os.path.basename(path)))
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as error:
        problems.append("%s: unreadable %s (%s)" % (label, os.path.basename(path), error))
        return None


def parse_stream(path, problems, label):
    """Returns (probe_record, cases). A damaged stream is a problem, not a pass."""
    probe = None
    summary = None
    cases = {}
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        problems.append("%s: probe stream missing or empty" % label)
        return None, {}
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for number, raw in enumerate(handle, 1):
            line = raw.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                problems.append("%s:%d: truncated JSON record" % (label, number))
                continue
            name = record.get("case")
            if not isinstance(name, str) or not name:
                problems.append("%s:%d: record without a case name" % (label, number))
                continue
            if name == "__probe":
                if probe is not None:
                    problems.append("%s:%d: duplicate __probe header" % (label, number))
                probe = record
                continue
            if name == "__summary":
                summary = record
                continue
            if name in cases:
                problems.append("%s:%d: duplicate case %s" % (label, number, name))
                continue
            status = record.get("status")
            if status not in STATUSES:
                problems.append("%s:%d: case %s has status %r" % (label, number, name, status))
                continue
            cases[name] = {"status": status, "detail": record.get("detail", "")}
    if probe is None:
        problems.append("%s: no __probe header" % label)
    if summary is None:
        problems.append("%s: no __summary record" % label)
    elif summary.get("failed") not in (0, None):
        problems.append("%s: summary reports %r failures" % (label, summary.get("failed")))
    if summary is not None and summary.get("cases") not in (None, len(cases)):
        problems.append("%s: summary counts %r cases, stream holds %d"
                        % (label, summary.get("cases"), len(cases)))
    return probe, cases


def compile_matrix(spec, evidence_root, identity):
    """Pure compiler: returns (report, problems)."""
    problems = []
    targets_out = []
    cells_total = {"pass": 0, "fail": 0, "pending": 0, "blocked": 0}

    for target in spec["targets"]:
        target_id = target["id"]
        cells = []
        if not target.get("expects_evidence"):
            for cell in spec["cells"]:
                cells.append({
                    "id": cell["id"],
                    "title": cell["title"],
                    "status": "pending",
                    "layer_required": cell["layer_required"],
                    "reason": target.get("pending_reason", "no producer for this target"),
                    "cases_required": len(cell["required_cases"]),
                    "cases_passed": 0,
                })
                cells_total["pending"] += 1
            targets_out.append({
                "id": target_id,
                "status": "pending",
                "runner": target.get("runner"),
                "producer": target.get("producer"),
                "measured": False,
                "reason": target.get("pending_reason", "no producer for this target"),
                "cells": cells,
            })
            continue

        label = "target %s" % target_id
        directory = os.path.join(evidence_root, target_id)
        if not os.path.isdir(directory):
            problems.append("%s: declared measurable but produced no evidence directory" % label)
            for cell in spec["cells"]:
                cells.append({
                    "id": cell["id"], "title": cell["title"], "status": "fail",
                    "layer_required": cell["layer_required"],
                    "reason": "no evidence for a target this run declared measurable",
                    "cases_required": len(cell["required_cases"]), "cases_passed": 0})
                cells_total["fail"] += 1
            targets_out.append({
                "id": target_id, "status": "measured", "runner": target.get("runner"),
                "producer": target.get("producer"), "measured": True,
                "evidence": None, "cells": cells})
            continue

        bound = {}
        record = load_json(os.path.join(directory, "identity.json"), problems, label)
        if record is None:
            for cell in spec["cells"]:
                cells.append({"id": cell["id"], "title": cell["title"], "status": "fail",
                              "layer_required": cell["layer_required"],
                              "reason": "identity.json missing",
                              "cases_required": len(cell["required_cases"]), "cases_passed": 0})
                cells_total["fail"] += 1
            targets_out.append({"id": target_id, "status": "measured", "runner": target.get("runner"),
                                "producer": target.get("producer"), "measured": True,
                                "evidence": None, "cells": cells})
            continue

        if record.get("source_sha") != identity["source_sha"]:
            problems.append("%s: identity source %r is not this source %r"
                            % (label, record.get("source_sha"), identity["source_sha"]))
        if str(record.get("run_id")) != str(identity["run_id"]):
            problems.append("%s: identity run %r is not this run %r"
                            % (label, record.get("run_id"), identity["run_id"]))
        if str(record.get("attempt")) != str(identity["attempt"]):
            problems.append("%s: identity attempt %r is not this attempt %r"
                            % (label, record.get("attempt"), identity["attempt"]))
        if record.get("platform") != target_id:
            problems.append("%s: identity platform %r does not match the target"
                            % (label, record.get("platform")))
        stream_layer = record.get("layer")
        if stream_layer not in LAYER_RANK:
            problems.append("%s: stream declares no usable layer (%r)" % (label, stream_layer))
            stream_layer = "module"

        probe_path = None
        for name in ("s06-matrix-probe", "s06-matrix-probe.exe"):
            candidate = os.path.join(directory, "probe", name)
            if os.path.isfile(candidate):
                probe_path = candidate
                break
        if probe_path is None:
            problems.append("%s: probe binary was not preserved with the evidence" % label)
        else:
            digest = sha256_file(probe_path)
            size = os.path.getsize(probe_path)
            bound["probe"] = {"path": os.path.relpath(probe_path, evidence_root),
                              "sha256": digest, "bytes": size}
            if record.get("probe_sha256") != digest:
                problems.append("%s: recorded probe digest does not match the preserved binary" % label)
            if int(record.get("probe_bytes", -1)) != size:
                problems.append("%s: recorded probe size does not match the preserved binary" % label)
            if size == 0:
                problems.append("%s: preserved probe binary is empty" % label)

        exit_path = os.path.join(directory, "probe.exit")
        if not os.path.isfile(exit_path):
            problems.append("%s: probe exit status was not recorded" % label)
        else:
            with open(exit_path, "r", encoding="utf-8") as handle:
                value = handle.read().strip()
            if value != "0":
                problems.append("%s: probe exited %r" % (label, value))

        stream_path = os.path.join(directory, "probe.jsonl")
        probe_record, cases = parse_stream(stream_path, problems, label)
        if os.path.isfile(stream_path):
            bound["probe_stream"] = {"path": os.path.relpath(stream_path, evidence_root),
                                     "sha256": sha256_file(stream_path),
                                     "bytes": os.path.getsize(stream_path)}
        if probe_record is not None and probe_record.get("platform") != target_id:
            problems.append("%s: probe ran as %r" % (label, probe_record.get("platform")))

        for cell in spec["cells"]:
            required = list(cell["required_cases"])
            missing = [name for name in required if name not in cases]
            failing = [name for name in required
                       if name in cases and cases[name]["status"] != "pass"]
            entry = {
                "id": cell["id"],
                "title": cell["title"],
                "layer_required": cell["layer_required"],
                "layer_measured": stream_layer,
                "cases_required": len(required),
                "cases_passed": len(required) - len(missing) - len(failing),
            }
            if LAYER_RANK[stream_layer] < LAYER_RANK[cell["layer_required"]]:
                entry["status"] = "blocked"
                entry["reason"] = ("%s evidence cannot fill a cell that requires a real %s handoff"
                                   % (stream_layer, cell["layer_required"]))
                cells_total["blocked"] += 1
            elif missing:
                entry["status"] = "fail"
                entry["reason"] = "required cases missing: " + ", ".join(sorted(missing))
                cells_total["fail"] += 1
            elif failing:
                entry["status"] = "fail"
                entry["reason"] = "; ".join("%s: %s" % (name, cases[name]["detail"])
                                            for name in sorted(failing))
                cells_total["fail"] += 1
            else:
                entry["status"] = "pass"
                entry["reason"] = "all %d required cases passed in this run" % len(required)
                cells_total["pass"] += 1
            cells.append(entry)

        targets_out.append({
            "id": target_id,
            "status": "measured",
            "runner": target.get("runner"),
            "producer": target.get("producer"),
            "measured": True,
            "layer": stream_layer,
            "evidence": {"directory": target_id, "bound": bound},
            "cells": cells,
        })

    measured = [t for t in targets_out if t["measured"]]
    report = {
        "schema": 1,
        "kind": "reader-final-s06-report",
        "source_sha": identity["source_sha"],
        "run": {"id": identity["run_id"], "attempt": identity["attempt"]},
        "spec": {"implementation_base": spec.get("implementation_base"), "cells": len(spec["cells"]),
                 "targets": len(spec["targets"])},
        "counts": counts(cells_total),
        "targets": targets_out,
        "problems": sorted(set(problems)),
    }
    # A declared-pending target grants nothing and blocks nothing: it is listed
    # separately. Acceptance covers only what this run actually measured.
    report["accepted"] = bool(measured) and not report["problems"] and cells_total["fail"] == 0 \
        and cells_total["blocked"] == 0
    report["measured_targets"] = len(measured)
    report["pending_targets"] = [t["id"] for t in targets_out if not t["measured"]]
    report["complete"] = report["accepted"] and cells_total["pending"] == 0
    report["limits"] = [
        "One GitHub Actions runner per measured target. No physical device is used for any target.",
        "The system open/share cell delivers through the platform clipboard or pasteboard and the installed "
        "desktop-drop adapter; no pointer-device drag gesture is synthesised.",
        "The cloud cell downloads the pinned fixture over HTTPS from the pinned commit and then imports that "
        "downloaded copy; the cloud transport product path belongs to the cloud-import producers and is not "
        "re-verified here.",
        "Targets without a job in this workflow stay pending and grant nothing.",
    ]
    return report, problems


def counts(totals):
    return {"pass": totals["pass"], "fail": totals["fail"], "pending": totals["pending"],
            "blocked": totals["blocked"]}


def write_report(report, output):
    os.makedirs(output, exist_ok=True)
    path = os.path.join(output, "report.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path

# --------------------------------------------------------------------- proof --
def _write_target(root, target_id, layer, cases, identity, probe_bytes=b"probe-binary",
                  probe_digest=None, exit_code="0", duplicate=None, drop=None):
    directory = os.path.join(root, target_id)
    os.makedirs(os.path.join(directory, "probe"), exist_ok=True)
    with open(os.path.join(directory, "probe", "s06-matrix-probe"), "wb") as handle:
        handle.write(probe_bytes)
    record = {
        "platform": target_id,
        "source_sha": identity["source_sha"],
        "run_id": identity["run_id"],
        "attempt": identity["attempt"],
        "layer": layer,
        "probe_sha256": probe_digest if probe_digest is not None
        else hashlib.sha256(probe_bytes).hexdigest(),
        "probe_bytes": len(probe_bytes),
    }
    with open(os.path.join(directory, "identity.json"), "w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2)
    names = [name for name in cases if name not in (drop or [])]
    with open(os.path.join(directory, "probe.jsonl"), "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"case": "__probe", "platform": target_id}) + "\n")
        for name in names:
            handle.write(json.dumps({"case": name, "status": "pass", "detail": "synthetic"}) + "\n")
        if duplicate:
            handle.write(json.dumps({"case": duplicate, "status": "fail", "detail": "synthetic"}) + "\n")
        handle.write(json.dumps({"case": "__summary", "failed": 0, "cases": len(names)}) + "\n")
    with open(os.path.join(directory, "probe.exit"), "w", encoding="utf-8") as handle:
        handle.write(exit_code + "\n")
    return directory


def _all_cases(spec):
    names = []
    for cell in spec["cells"]:
        names.extend(cell["required_cases"])
    return names


def selftest(spec, output):
    identity = {"source_sha": "a" * 40, "run_id": "100", "attempt": "1"}
    results = []

    def record(name, ok, detail):
        results.append({"case": name, "status": "pass" if ok else "fail", "detail": detail})
        print(json.dumps(results[-1]))

    work = os.path.join(output, "selftest")
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)

    def fresh(label, layer="host", **kwargs):
        root = os.path.join(work, label)
        os.makedirs(root, exist_ok=True)
        for target in spec["targets"]:
            if not target.get("expects_evidence"):
                continue
            _write_target(root, target["id"], layer, _all_cases(spec), identity, **kwargs)
        return root

    # 1. A clean host stream satisfies every cell.
    root = fresh("clean_host")
    report, problems = compile_matrix(spec, root, identity)
    record("accepts_same_source_same_run_host_evidence",
           report["accepted"] and not problems, "accepted=%s problems=%d" % (report["accepted"], len(problems)))

    # 2. A module-level stream may never fill a host cell.
    root = fresh("module_only", layer="module")
    report, problems = compile_matrix(spec, root, identity)
    blocked = [cell["id"] for target in report["targets"] for cell in target["cells"]
               if cell["status"] == "blocked"]
    record("refuses_module_evidence_for_host_cells",
           not report["accepted"] and len(blocked) == 5 * len([t for t in spec["targets"] if t.get("expects_evidence")]),
           "blocked cells=%d accepted=%s" % (len(blocked), report["accepted"]))

    # 3. Foreign source, foreign run, foreign attempt.
    for field, label in (("source_sha", "source"), ("run_id", "run"), ("attempt", "attempt")):
        root = fresh("foreign_" + label)
        for target in spec["targets"]:
            if not target.get("expects_evidence"):
                continue
            path = os.path.join(root, target["id"], "identity.json")
            with open(path, "r", encoding="utf-8") as handle:
                value = json.load(handle)
            value[field] = "deadbeef" if field != "attempt" else "9"
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(value, handle)
        report, problems = compile_matrix(spec, root, identity)
        record("refuses_foreign_" + label, not report["accepted"] and bool(problems),
               "problems=%d" % len(problems))

    # 4. A required case that is simply absent.
    root = fresh("missing_case", drop=["system_handoff_imports_delivered_file"])
    report, problems = compile_matrix(spec, root, identity)
    failed = [cell["id"] for target in report["targets"] for cell in target["cells"]
              if cell["status"] == "fail"]
    record("refuses_missing_required_case",
           not report["accepted"] and failed and all(c == "system_open_share" for c in failed),
           "failed cells=%s" % (sorted(set(failed)),))

    # 5. A required case that ran and failed.
    root = fresh("failing_case")
    for target in spec["targets"]:
        if not target.get("expects_evidence"):
            continue
        path = os.path.join(root, target["id"], "probe.jsonl")
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
        with open(path, "w", encoding="utf-8") as handle:
            for line in lines:
                record_value = json.loads(line)
                if record_value.get("case") == "bad_empty_rejected":
                    record_value["status"] = "fail"
                handle.write(json.dumps(record_value) + "\n")
    report, problems = compile_matrix(spec, root, identity)
    failed_cells = [cell["id"] for target in report["targets"] for cell in target["cells"]
                    if cell["status"] == "fail"]
    record("refuses_failed_required_case",
           not report["accepted"] and set(failed_cells) == {"bad_file"},
           "failed cells=%s problems=%d" % (sorted(set(failed_cells)), len(problems)))

    # 6. A duplicated case record is damage, not a second chance.
    root = fresh("duplicate_case", duplicate="local_file_private_path_import")
    report, problems = compile_matrix(spec, root, identity)
    record("refuses_duplicate_case_record",
           not report["accepted"] and any("duplicate case" in problem for problem in problems),
           "problems=%d" % len(problems))

    # 7. A recorded digest that does not match the preserved binary.
    root = fresh("digest_mismatch", probe_digest="0" * 64)
    report, problems = compile_matrix(spec, root, identity)
    record("refuses_probe_digest_mismatch", not report["accepted"] and bool(problems),
           "problems=%d" % len(problems))

    # 8. An empty stream.
    root = fresh("empty_stream")
    for target in spec["targets"]:
        if not target.get("expects_evidence"):
            continue
        open(os.path.join(root, target["id"], "probe.jsonl"), "w").close()
    report, problems = compile_matrix(spec, root, identity)
    record("refuses_empty_stream", not report["accepted"] and bool(problems), "problems=%d" % len(problems))

    # 9. A non-zero probe exit status.
    root = fresh("exit_failure", exit_code="1")
    report, problems = compile_matrix(spec, root, identity)
    record("refuses_probe_exit_failure", not report["accepted"] and bool(problems),
           "problems=%d" % len(problems))

    # 10. A measurable target with no evidence at all.
    root = fresh("no_evidence")
    shutil.rmtree(os.path.join(root, "macos"))
    report, problems = compile_matrix(spec, root, identity)
    record("refuses_missing_target_evidence", not report["accepted"] and bool(problems),
           "problems=%d" % len(problems))

    failed = [item for item in results if item["status"] != "pass"]
    print(json.dumps({"case": "__summary", "failed": len(failed), "cases": len(results)}))
    return 0 if not failed else 1


# ----------------------------------------------------------------------- cli --
def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    compile_parser = sub.add_parser("compile")
    compile_parser.add_argument("--spec", required=True)
    compile_parser.add_argument("--evidence", required=True)
    compile_parser.add_argument("--output", required=True)
    compile_parser.add_argument("--source", default=os.environ.get("GITHUB_SHA", ""))
    compile_parser.add_argument("--run", default=os.environ.get("GITHUB_RUN_ID", ""))
    compile_parser.add_argument("--attempt", default=os.environ.get("GITHUB_RUN_ATTEMPT", ""))
    selftest_parser = sub.add_parser("selftest")
    selftest_parser.add_argument("--spec", required=True)
    selftest_parser.add_argument("--output", required=True)
    args = parser.parse_args()

    problems = []
    spec = load_json(args.spec, problems, "spec")
    if spec is None:
        for problem in problems:
            print("problem: " + problem, file=sys.stderr)
        return 1

    if args.command == "selftest":
        os.makedirs(args.output, exist_ok=True)
        return selftest(spec, args.output)

    identity = {"source_sha": args.source, "run_id": args.run, "attempt": args.attempt}
    for field, value in identity.items():
        if not value:
            problems.append("identity field %s is empty" % field)
    report, problems = compile_matrix(spec, args.evidence, identity)
    report["problems"] = sorted(set(report["problems"] + problems))
    report["accepted"] = report["accepted"] and not report["problems"]
    path = write_report(report, args.output)
    for problem in report["problems"]:
        print("problem: " + problem, file=sys.stderr)
    print("report: %s (pass %d / fail %d / pending %d / blocked %d, accepted=%s)"
          % (path, report["counts"]["pass"], report["counts"]["fail"],
             report["counts"]["pending"], report["counts"]["blocked"], report["accepted"]))
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
