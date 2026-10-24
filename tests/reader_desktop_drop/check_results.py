#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Validate the named acceptance cases of one platform and bind them to this
source revision, run, attempt and the exact binaries/logs that produced them.

Supplemental logs (a hook build and a sanitizer build on Windows) are merged by
case name with fail > pass > skip precedence, and each supplemental log must
carry the complete case set on its own, so a crashed sanitizer run can never be
masked by a green primary run.
"""
import argparse
import hashlib
import json
import os
import sys

PORTABLE_CASES = [
    "uri_file_existing", "uri_directory_not_recursed", "uri_missing_path", "uri_percent_encoded_utf8",
    "uri_localhost_is_local", "uri_remote_host", "uri_remote_url_https", "uri_remote_url_smb",
    "uri_virtual_trash", "uri_virtual_mtp", "uri_bad_percent_hex", "uri_short_percent", "uri_percent_nul",
    "uri_query_rejected", "uri_fragment_rejected", "uri_space_rejected", "uri_relative_rejected",
    "uri_control_byte_rejected", "uri_scheme_too_short", "uri_percent_bad_utf8", "uri_percent_overlong_utf8",
    "uri_percent_surrogate_utf8", "uri_utf8_raw_invalid", "list_bom_comment_blank", "list_cr_crlf_duplicates",
    "list_empty_is_empty", "list_blank_only_is_empty", "argument_null_with_size", "gnome_copy_prefix",
    "gnome_cut_prefix", "limit_payload_too_large", "limit_item_cap", "limit_path_too_long",
    "cancel_after_first_entry", "reentrant_parse_in_cancel", "control_struct_size_rejected",
    "origin_range_rejected", "utf16_unpaired_surrogate", "utf16_lines_basic", "utf16_surrogate_pair",
    "utf16_layout_rejected", "utf16_payload_too_large", "utf8_list_two_entries", "utf8_list_null_entry",
    "utf8_list_bad_encoding_item", "get_info_struct_size", "get_item_out_of_range", "get_item_struct_size",
    "get_info_null_request", "release_null_is_safe", "concurrent_parse", "status_names_complete",
]

PLATFORM_CASES = {
    "windows": [
        "ole_initialize", "fixtures_created", "window_created", "attach_real_window", "attach_null_window",
        "attach_bad_options", "attach_needs_ole_per_thread",
        "clipboard_hdrop_unicode_paths", "clipboard_empty", "clipboard_text_lines",
        "clipboard_unpaired_surrogate", "clipboard_bom_skipped", "clipboard_relative_text",
        "clipboard_directory", "clipboard_duplicates", "clipboard_item_cap", "clipboard_long_path",
        "clipboard_cancel", "request_outlives_clipboard",
        "shell_data_object_created", "shell_drop_delivers_file", "object_hdrop_delivers",
        "object_unicode_text_delivers", "object_virtual_descriptor", "object_unsupported_format",
        "request_outlives_data_object",
        "reject_text_without_terminator", "reject_text_odd_bytes", "reject_text_short_global",
        "accept_text_exact_terminator", "reject_file_group_short_header",
        "reject_file_group_beyond_allocation", "reject_file_group_extreme_count",
        "reject_file_group_empty", "reject_hdrop_short_header", "reject_hdrop_pfiles_out_of_range",
        "reject_hdrop_pfiles_before_header", "reject_hdrop_wide_unterminated",
        "reject_hdrop_ansi_unterminated", "accept_hdrop_ansi_list", "reject_hdrop_wide_truncated_unit",
        "reject_clipboard_hdrop_invalid_pfiles",
        "detach_from_other_thread", "detach_inside_callback", "window_destroyed_before_detach",
        "window_proc_restored_after_detach", "com_object_reclaimed_after_window_destroy",
        "deliver_null_object", "detach_owner_thread",
    ],
    "linux": [
        "gtk_init", "gtk_window_created", "fixtures_created", "attach_real_widget",
        "drop_target_list_registered", "attach_null_widget", "attach_while_context_owned",
        "clipboard_uri_one_file", "clipboard_uri_unicode_name", "clipboard_uri_directory",
        "clipboard_remote_url", "clipboard_remote_host", "clipboard_virtual_scheme", "clipboard_bad_percent",
        "clipboard_bad_utf8", "clipboard_too_long_path", "clipboard_item_cap", "clipboard_cancel",
        "clipboard_empty", "selection_data_unicode", "selection_wrong_target", "drag_signal_delivers",
        "request_outlives_selection_data", "clipboard_gnome_copy", "detach_from_other_thread",
        "detach_inside_callback", "widget_destroyed_before_detach", "detach_owner_thread",
    ],
    "macos": [
        "appkit_available", "fixtures_created", "host_view_created", "attach_real_view",
        "drag_types_registered", "attach_null_view", "pasteboard_file_url", "pasteboard_unicode_name",
        "pasteboard_directory", "pasteboard_remote_url", "pasteboard_missing_path",
        "pasteboard_string_lines", "pasteboard_remote_host", "pasteboard_virtual_scheme",
        "pasteboard_bad_percent", "pasteboard_bad_utf8", "pasteboard_too_long_path",
        "pasteboard_item_cap", "pasteboard_cancel", "pasteboard_empty", "drag_entered_copy",
        "drag_perform_delivers", "drag_overlay_present", "request_outlives_pasteboard",
        "detach_inside_callback", "detach_from_other_thread", "view_detached_before_destroy",
        "detach_owner_thread",
    ],
}

# A skip is only admissible where the environment may legitimately lack the
# facility, and the reason is recorded verbatim in the report.
ALLOWED_SKIPS = {
    "windows": {name: "clipboard" for name in PLATFORM_CASES["windows"] if "clipboard" in name},
    "linux": {},
    "macos": {},
}

SANITIZER_MARKERS = ("AddressSanitizer", "LeakSanitizer", "MemorySanitizer", "ThreadSanitizer")

RANK = {"fail": 3, "pass": 2, "skip": 1}


def parse_jsonl(path, label, problems):
    cases = []
    seen = set()
    summaries = []
    noise = []
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for number, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                # Toolkit chatter (GTK/AT-SPI warnings) may share the stream; a
                # truncated case record still counts as damage.
                if line.startswith("{"):
                    problems.append(f"{label}:{number}: truncated JSON: {line[:120]}")
                else:
                    noise.append(line[:120])
                continue
            name = record.get("case")
            if name is None:
                problems.append(f"{label}:{number}: missing case name")
                continue
            if name == "__summary":
                summaries.append(record)
                continue
            if name in seen:
                problems.append(f"{label}:{number}: duplicate case {name}")
                continue
            seen.add(name)
            status = record.get("status")
            if status not in ("pass", "fail", "skip"):
                problems.append(f"{label}:{number}: bad status {status!r}")
                continue
            cases.append({"name": name, "status": status, "detail": record.get("detail", "")})
    if not summaries:
        problems.append(f"{label}: no __summary line")
    return cases, summaries, noise


def require_complete(label, cases, required, problems):
    names = {case["name"] for case in cases}
    for name in required:
        if name not in names:
            problems.append(f"{label}: case missing: {name}")


def merge(source_cases):
    merged = {}
    for label, cases in source_cases:
        for case in cases:
            current = merged.get(case["name"])
            if current is None or RANK[case["status"]] > RANK[current["status"]]:
                merged[case["name"]] = {"name": case["name"], "status": case["status"],
                                        "detail": case["detail"], "source": label}
            elif RANK[case["status"]] == RANK[current["status"]] and case["status"] == "fail":
                merged[case["name"]]["detail"] += " | " + case["detail"]
    return sorted(merged.values(), key=lambda case: case["name"])


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan_file(path, problems):
    if not os.path.isfile(path):
        problems.append(f"scan file missing: {path}")
        return
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for number, line in enumerate(handle, 1):
            for marker in SANITIZER_MARKERS:
                if marker in line:
                    problems.append(f"sanitizer report in {path}:{number}: {line.strip()[:160]}")
                    return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", required=True, choices=["windows", "linux", "macos"])
    parser.add_argument("--probe-log", required=True)
    parser.add_argument("--portable-log", required=True)
    parser.add_argument("--extra-probe-log", action="append", default=[])
    parser.add_argument("--extra-portable-log", action="append", default=[])
    parser.add_argument("--scan", action="append", default=[])
    parser.add_argument("--exe", required=True, help="platform probe binary")
    parser.add_argument("--portable-exe", required=True)
    parser.add_argument("--root", required=True, help="artifact root, e.g. build/desktop-drop")
    parser.add_argument("--output", required=True)
    parser.add_argument("--job", default=os.environ.get("GITHUB_JOB", ""))
    args = parser.parse_args()

    problems = []
    noise_all = []
    probe_streams = [("probe", args.probe_log)]
    portable_streams = [("portable", args.portable_log)]
    for path in args.extra_probe_log:
        probe_streams.append((os.path.basename(path), path))
    for path in args.extra_portable_log:
        portable_streams.append((os.path.basename(path), path))
    for _, path in probe_streams + portable_streams:
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            problems.append(f"log missing or empty: {path}")

    probe_sets = []
    portable_sets = []
    for label, path in probe_streams:
        if not os.path.isfile(path):
            continue
        cases, summaries, noise = parse_jsonl(path, label, problems)
        noise_all.extend(noise)
        require_complete(label, cases, PLATFORM_CASES[args.platform], problems)
        for summary in summaries:
            if summary.get("failed", 0) != 0:
                problems.append(f"{label}: summary reports failures: {summary}")
        probe_sets.append((label, cases))
    for label, path in portable_streams:
        if not os.path.isfile(path):
            continue
        cases, summaries, noise = parse_jsonl(path, label, problems)
        noise_all.extend(noise)
        require_complete(label, cases, PORTABLE_CASES, problems)
        for summary in summaries:
            if summary.get("failed", 0) != 0:
                problems.append(f"{label}: summary reports failures: {summary}")
        portable_sets.append((label, cases))

    probe_cases = merge(probe_sets)
    portable_cases = merge(portable_sets)

    allowed = ALLOWED_SKIPS[args.platform]
    for case in probe_cases + portable_cases:
        if case["status"] == "fail":
            problems.append(f"case failed: {case['name']} ({case['source']}): {case['detail']}")
        elif case["status"] == "skip":
            reason = allowed.get(case["name"])
            if not reason or reason not in case["detail"]:
                problems.append(f"unplanned skip: {case['name']} ({case['source']}): {case['detail']}")

    for path in args.scan:
        scan_file(path, problems)

    if not os.path.isfile(args.exe) or os.path.getsize(args.exe) == 0:
        problems.append(f"missing or empty probe binary: {args.exe}")
    if not os.path.isfile(args.portable_exe) or os.path.getsize(args.portable_exe) == 0:
        problems.append(f"missing or empty portable binary: {args.portable_exe}")

    source_sha = os.environ.get("GITHUB_SHA", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "")
    if not source_sha:
        problems.append("GITHUB_SHA is not set")

    binding_paths = [
        os.path.relpath(args.exe, args.root),
        os.path.relpath(args.portable_exe, args.root),
    ]
    for _, path in probe_streams + portable_streams:
        binding_paths.append(os.path.relpath(path, args.root))
    for path in args.scan:
        binding_paths.append(os.path.relpath(path, args.root))
    for relative in ("logs/module-configure.log", "logs/module-build.log", "logs/module-install.log",
                     "logs/consumer-configure.log", "logs/consumer-build.log",
                     "logs/examples-configure.log", "logs/examples-build.log"):
        binding_paths.append(relative)

    bindings = []
    seen_paths = set()
    for relative in binding_paths:
        relative = relative.replace("\\", "/")
        if relative in seen_paths:
            continue
        seen_paths.add(relative)
        path = os.path.join(args.root, relative)
        if not os.path.isfile(path):
            problems.append(f"binding file missing: {relative}")
            continue
        bindings.append({"path": relative, "sha256": sha256_file(path), "bytes": os.path.getsize(path)})

    report = {
        "schema": 1,
        "kind": "reader-desktop-drop-report",
        "platform": args.platform,
        "source_sha": source_sha,
        "run": {"id": run_id, "attempt": attempt, "job": args.job},
        "cases": {"probe": probe_cases, "portable": portable_cases},
        "streams": {"probe": [label for label, _ in probe_streams],
                    "portable": [label for label, _ in portable_streams],
                    "scanned": list(args.scan)},
        "counts": {
            "probe": len(probe_cases),
            "portable": len(portable_cases),
            "failed": sum(1 for c in probe_cases + portable_cases if c["status"] == "fail"),
            "skipped": [c["name"] for c in probe_cases + portable_cases if c["status"] == "skip"],
        },
        "bindings": bindings,
        "toolkit_noise": noise_all[:20],
        "limits": [
            "One GitHub Actions runner per platform; no physical device, no interactive drag session.",
            "Windows drops are delivered through the adapter entry OLE calls for IDropTarget::Drop with a real "
            "shell data object; no pointer-device drag is started.",
            "Windows memory safety is asserted by an AddressSanitizer build of the same probe and by a hook "
            "build that counts live COM targets; the hook counters are compiled out of the installed binary.",
            "GTK payloads travel through a real X11 clipboard and a real drop destination; the drag gesture "
            "itself is not synthesised.",
            "AppKit payloads travel through a real private NSPasteboard and a real NSDraggingInfo double into "
            "the installed destination view.",
        ],
        "accepted": not problems,
        "problems": problems,
    }
    os.makedirs(args.output, exist_ok=True)
    target = os.path.join(args.output, "report.json")
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    for problem in problems:
        print(f"problem: {problem}", file=sys.stderr)
    print(f"report: {target} ({len(probe_cases)} probe + {len(portable_cases)} portable cases, "
          f"{len(problems)} problems)")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
