#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Validate the named acceptance cases of one platform and bind them to this
source revision, run, attempt and the exact binaries/logs that produced them."""
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
        "request_outlives_data_object", "detach_from_other_thread", "detach_inside_callback",
        "window_destroyed_before_detach", "deliver_null_object", "detach_owner_thread",
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


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", required=True, choices=["windows", "linux", "macos"])
    parser.add_argument("--probe-log", required=True)
    parser.add_argument("--portable-log", required=True)
    parser.add_argument("--exe", required=True, help="platform probe binary")
    parser.add_argument("--portable-exe", required=True)
    parser.add_argument("--root", required=True, help="artifact root, e.g. build/desktop-drop")
    parser.add_argument("--output", required=True)
    parser.add_argument("--job", default=os.environ.get("GITHUB_JOB", ""))
    args = parser.parse_args()

    problems = []
    probe_cases, probe_summaries, probe_noise = parse_jsonl(args.probe_log, "probe", problems)
    portable_cases, portable_summaries, portable_noise = parse_jsonl(args.portable_log, "portable", problems)
    probe_names = {case["name"] for case in probe_cases}
    portable_names = {case["name"] for case in portable_cases}

    for name in PLATFORM_CASES[args.platform]:
        if name not in probe_names:
            problems.append(f"platform case missing: {name}")
    for name in PORTABLE_CASES:
        if name not in portable_names:
            problems.append(f"portable case missing: {name}")

    allowed = ALLOWED_SKIPS[args.platform]
    unplanned_skips = []
    for case in probe_cases + portable_cases:
        if case["status"] == "fail":
            problems.append(f"case failed: {case['name']}: {case['detail']}")
        if case["status"] == "skip":
            if case["name"] in allowed and allowed[case["name"]] in case["detail"]:
                continue
            unplanned_skips.append(case["name"])
    for name in unplanned_skips:
        problems.append(f"unplanned skip: {name}")

    for summary in probe_summaries + portable_summaries:
        if summary.get("failed", 0) != 0:
            problems.append(f"summary reports failures: {summary}")

    if not os.path.isfile(args.exe) or os.path.getsize(args.exe) == 0:
        problems.append(f"missing or empty probe binary: {args.exe}")
    if not os.path.isfile(args.portable_exe) or os.path.getsize(args.portable_exe) == 0:
        problems.append(f"missing or empty portable binary: {args.portable_exe}")

    source_sha = os.environ.get("GITHUB_SHA", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "")
    if not source_sha:
        problems.append("GITHUB_SHA is not set")

    bindings = []
    for relative in (
        os.path.relpath(args.exe, args.root),
        os.path.relpath(args.portable_exe, args.root),
        os.path.relpath(args.probe_log, args.root),
        os.path.relpath(args.portable_log, args.root),
        "logs/module-configure.log",
        "logs/module-build.log",
        "logs/module-install.log",
        "logs/consumer-configure.log",
        "logs/consumer-build.log",
        "logs/examples-configure.log",
        "logs/examples-build.log",
    ):
        path = os.path.join(args.root, relative)
        if not os.path.isfile(path):
            problems.append(f"binding file missing: {relative}")
            continue
        bindings.append({"path": relative.replace("\\", "/"), "sha256": sha256_file(path),
                         "bytes": os.path.getsize(path)})

    report = {
        "schema": 1,
        "kind": "reader-desktop-drop-report",
        "platform": args.platform,
        "source_sha": source_sha,
        "run": {"id": run_id, "attempt": attempt, "job": args.job},
        "cases": {"probe": probe_cases, "portable": portable_cases},
        "counts": {
            "probe": len(probe_cases),
            "portable": len(portable_cases),
            "failed": sum(1 for c in probe_cases + portable_cases if c["status"] == "fail"),
            "skipped": [c["name"] for c in probe_cases + portable_cases if c["status"] == "skip"],
        },
        "bindings": bindings,
        "toolkit_noise": (probe_noise + portable_noise)[:20],
        "limits": [
            "One GitHub Actions runner per platform; no physical device, no interactive drag session.",
            "Windows drops are delivered through the adapter entry OLE calls for IDropTarget::Drop with a real "
            "shell data object; no pointer-device drag is started.",
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
