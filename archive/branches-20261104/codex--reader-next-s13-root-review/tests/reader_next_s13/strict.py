#!/usr/bin/env python3
"""S13 strict summary: authenticate the artifacts produced by this exact run.

Runs in Actions only. The artifact identity (id, bytes, digest, expiry) comes
from the Actions API for this run id; the content comes from the downloaded
artifact and is checked against the pinned inputs and the per-platform named
checks. A missing observation is never a pass.
"""
import argparse
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run import Checks, read_json, sha256_file, write_json  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from check_parallel_integration import download_artifact_zip, fetch, pages


def authenticated_zip(item, root):
    """Consume the actual API ZIP, never an unauthenticated expanded directory."""
    assert item.get("expired") is False
    assert datetime.fromisoformat(item["expires_at"].replace("Z", "+00:00")) > datetime.now(timezone.utc)
    root.mkdir(parents=True, exist_ok=True)
    archive = root / (str(item["id"]) + ".zip")
    with archive.open("w+b") as stream:
        download_artifact_zip(item["id"], stream)
    assert archive.stat().st_size == item["size_in_bytes"], "ZIP byte count"
    assert "sha256:" + sha256_file(archive) == item["digest"], "ZIP digest"
    destination = root / item["name"]
    with zipfile.ZipFile(archive) as zipped:
        names = zipped.namelist()
        assert len(names) == len(set(names)), "duplicate ZIP members"
        for info in zipped.infolist():
            # ZipInfo normalizes Windows separators while reading too. Validate
            # the raw central-directory name before trusting its normalized form.
            name = info.orig_filename
            assert name and not name.startswith("/") and "\\" not in name and ":" not in name
            assert ".." not in name.split("/") and (info.external_attr >> 16) & 0o170000 != 0o120000
        zipped.extractall(destination)
    return destination

REQUIRED_PREFIXES = (
    "fixture:",
    "fixture-base:",
    "pinned_identity:",
    "leading_slash_member_present:",
    "original_failure_preserved:",
    "candidate_opens:",
    "ids_are_member_names:",
    "page_set_matches_oracle:",
    "page_order_matches_reader_rule:",
    "geometry_matches_independent_decoder:",
    "render_matches_member_pixels:",
    "reopen_in_process:",
    "reopen_second_process:",
    "point_capture_keeps_page_identity:",
    "point_resolve_no_invented_range:",
    "page_bounds_refusal:",
    "library_page_identity:",
    "archive_bytes_unchanged:",
    "suite_results_identical",
)


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", required=True)
    parser.add_argument("--download", required=True)
    parser.add_argument("--pinned", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    api = read_json(args.artifacts)
    pinned = read_json(args.pinned)
    root = Path(args.download)
    checks = Checks("strict")
    run = fetch("actions/runs/" + args.run_id + "/attempts/" + args.run_attempt)
    jobs = pages("actions/runs/" + args.run_id + "/attempts/" + args.run_attempt + "/jobs", "jobs")
    checks.require("run_source_attempt", run.get("head_sha") == args.source_sha and
                   str(run.get("run_attempt")) == args.run_attempt and
                   run.get("path", "").split("@")[0] == ".github/workflows/reader-next-s13.yml")
    for platform in ("linux", "windows"):
        producers = [job for job in jobs if job.get("name") == "candidate-" + platform]
        checks.require("producer_success:" + platform, len(producers) == 1 and
                       producers[0].get("head_sha") == args.source_sha and
                       producers[0].get("status") == "completed" and producers[0].get("conclusion") == "success",
                       producers)
    expected_names = {"reader-next-s13-%s-%s-%s" % (platform, args.run_id, args.run_attempt)
                      for platform in ("linux", "windows")}
    selected = [item for item in api.get("artifacts", [])
                if item.get("name", "") in expected_names and
                str(item.get("workflow_run", {}).get("id")) == str(args.run_id)]
    checks.require("two_platform_artifacts", len(selected) == 2,
                   {"count": len(selected), "names": [item["name"] for item in selected]})
    checks.require("exact_artifact_names", {item["name"] for item in selected} == expected_names)
    identity = []
    summaries = {}
    inputs = {}
    reports = {}
    for item in selected:
        name = item["name"]
        platform = name.split("-")[3] if len(name.split("-")) > 3 else "unknown"
        identity.append({"name": name, "id": item.get("id"), "bytes": item.get("size_in_bytes"),
                         "digest": item.get("digest"), "expires_at": item.get("expires_at"),
                         "head_sha": item.get("workflow_run", {}).get("head_sha"),
                         "workflow_run_id": item.get("workflow_run", {}).get("id")})
        checks.require("artifact_run_bound:" + platform,
                       str(item.get("workflow_run", {}).get("head_sha")) == args.source_sha and
                       str(item.get("workflow_run", {}).get("id")) == str(args.run_id),
                       {"head_sha": item.get("workflow_run", {}).get("head_sha")})
        checks.require("artifact_identity_recorded:" + platform,
                       bool(item.get("id")) and (item.get("size_in_bytes") or 0) > 0 and
                       str(item.get("digest", "")).startswith("sha256:") and bool(item.get("expires_at")),
                       {"id": item.get("id"), "bytes": item.get("size_in_bytes"),
                        "digest": item.get("digest"), "expires_at": item.get("expires_at")})
        artifact_dir = authenticated_zip(item, root)
        if not (artifact_dir / "reports/programs.json").is_file():
            checks.require("actual_program_report_present:" + platform, False)
            continue
        programs = read_json(artifact_dir / "reports/programs.json")["programs"]
        checks.require("three_actual_programs:" + platform, len(programs) == 3 and
                       len({record["path"] for record in programs}) == 3)
        for record in programs:
            path = record["path"].replace("\\", "/")
            assert path.startswith("build/s13/") and ".." not in path.split("/")
            binary = artifact_dir / path.removeprefix("build/s13/")
            checks.require("actual_program:" + platform + ":" + path,
                           binary.is_file() and binary.stat().st_size == record.get("bytes") and
                           sha256_file(binary) == record.get("sha256"), record)
        report_path = artifact_dir / "reports" / "summary.json"
        if not report_path.is_file():
            checks.require("summary_present:" + platform, False, {"path": str(report_path)})
            continue
        summary = read_json(report_path)
        summaries[platform] = summary
        checks.require("summary_accepted:" + platform,
                       summary.get("accepted") is True and summary.get("source_sha") == args.source_sha and
                       str(summary.get("run_id")) == str(args.run_id) and
                       str(summary.get("run_attempt")) == str(args.run_attempt),
                       {"accepted": summary.get("accepted"), "source_sha": summary.get("source_sha"),
                        "run_id": summary.get("run_id"), "run_attempt": summary.get("run_attempt")})
        checks.require("summary_named_checks:" + platform,
                       summary.get("named_check_count", 0) > 0 and not summary.get("failed_checks"),
                       {"named_check_count": summary.get("named_check_count"),
                        "failed": summary.get("failed_checks")})
        names = []
        expected_parts = {"checks-workspace.json", "checks-fixtures.json", "checks-real.json", "checks-suite.json"}
        checks.require("exact_part_inventory:" + platform,
                       len(summary.get("parts", [])) == 4 and
                       {Path(part).name for part in summary.get("parts", [])} == expected_parts)
        for part in summary.get("parts", []):
            part_path = artifact_dir / "reports" / Path(part).name
            payload = read_json(part_path)
            entries = payload.get("checks", [])
            part_names = [entry["name"] for entry in entries]
            checks.require("part_complete:" + platform + ":" + part_path.name,
                           payload.get("accepted") is True and payload.get("failed") == [] and
                           payload.get("check_count") == len(entries) > 0 and
                           len(set(part_names)) == len(part_names) and all(entry.get("ok") is True for entry in entries))
            names.extend(part_names)
        checks.require("exact_named_count:" + platform, summary.get("named_check_count") == len(names))
        missing = [prefix for prefix in REQUIRED_PREFIXES if not any(name.startswith(prefix) or name == prefix for name in names)]
        checks.require("no_missing_observation:" + platform, not missing,
                       {"checks_seen": len(names), "missing": missing})
        for entry in pinned["files"]:
            local = artifact_dir / "inputs" / entry["path"]
            if not local.is_file():
                checks.require("pinned_input_inside_artifact:" + platform + ":" + entry["id"], False, {"path": str(local)})
                continue
            digest = sha256_file(local)
            inputs.setdefault(entry["id"], {})[platform] = {"sha256": digest, "bytes": local.stat().st_size}
            checks.require("pinned_input_inside_artifact:%s:%s" % (platform, entry["id"]),
                           digest == entry["sha256"] and local.stat().st_size == entry["bytes"],
                           {"sha256": digest, "bytes": local.stat().st_size})
        for entry in pinned["files"]:
            report = artifact_dir / "reports" / "real" / ("candidate-%s-run1.json" % entry["id"])
            if report.is_file():
                reports.setdefault(entry["id"], {})[platform] = read_json(report)
    checks.require("both_platforms_present", sorted(summaries) == ["linux", "windows"], {"present": sorted(summaries)})
    for identifier, values in inputs.items():
        checks.require("same_original_zip_both_platforms:" + identifier,
                       len(values) == 2 and len({item["sha256"] for item in values.values()}) == 1,
                       values)
    def comparable(report):
        # The echoed input path uses the platform separator unless the producer
        # normalised it; compare the observations, not the spelling of the path.
        copy = dict(report)
        if "input" in copy:
            copy["input"] = str(copy["input"]).replace("\\", "/")
        return copy

    for identifier, values in reports.items():
        normalized = {platform: comparable(report) for platform, report in values.items()}
        checks.require("cross_platform_identical:" + identifier,
                       len(values) == 2 and normalized.get("linux") == normalized.get("windows"),
                       {"platforms": sorted(values),
                        "render_equal": values.get("linux", {}).get("render") == values.get("windows", {}).get("render"),
                        "pages": sorted({str(report.get("page_count")) for report in values.values()})})
    payload = checks.payload({"source_sha": args.source_sha, "run_id": args.run_id,
                              "run_attempt": args.run_attempt, "artifacts": identity,
                              "platforms": sorted(summaries)})
    write_json(args.out, payload)
    print(json.dumps({"accepted": payload["accepted"], "failed": payload["failed"],
                      "artifacts": [{"name": i["name"], "id": i["id"], "bytes": i["bytes"], "digest": i["digest"]} for i in identity]}))
    return 0 if payload["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
