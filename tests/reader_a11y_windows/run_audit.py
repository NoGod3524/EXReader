#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Windows keyboard and accessibility audit for the fixed Win32 reader host.

Launches the packaged host exactly as a user would, drives the shelf, import,
details, reading, annotation and size commands with the keyboard only, and
records raw UI Automation trees, the key trace and screenshots.

The audit is separate from acceptance: audit_completed says the evidence was
collected on this source, accessibility_accepted says no blocking finding was
measured. Screen-reader acceptance needs a human NVDA/Narrator pass and stays
unverified here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import evidence
import flows
import keyboard as keyboard_module
import uia_layer
import w32
from host import Host, HostStartError
from session import Session

WORKFLOW = ".github/workflows/reader-a11y-windows.yml"
IMPLEMENTATION_START = "f43baf9182d75907c0cb5d6f77048f27bca8c950"
SDK_FROZEN = "9854061be331fe603a1822d9b2b36ee357154927"
PRODUCT_SCHEMA = "f32bb8aa18ed3de286900f19ce4230fd93435dd0"

SCOPE = [
    {"id": "shelf", "name": "书架", "covers": "book list, search, refresh, details entry"},
    {"id": "import", "name": "导入", "covers": "path field, import command, result text"},
    {"id": "organize", "name": "整理", "covers": "details dialog fields, checkbox, buttons, focus return"},
    {"id": "reading", "name": "阅读", "covers": "page region, page turning, position text, selection"},
    {"id": "annotation", "name": "标注", "covers": "annotation list, comment field, add/jump/delete"},
    {"id": "settings", "name": "设置", "covers": "font and zoom commands and their persistence"},
    {"id": "keyboard", "name": "键盘", "covers": "tab order, reverse order, command coverage, focus coherence"},
]

PROVIDER_PATTERNS = {
    "WM_GETOBJECT": r"WM_GETOBJECT",
    "UiaReturnRawElementProvider": r"UiaReturnRawElementProvider",
    "IAccessible": r"\bIAccessible\b",
    "NotifyWinEvent": r"NotifyWinEvent",
    "UIAutomation": r"\bIUIAutomation\b|\bUIAutomation\b",
    "WM_UPDATEUISTATE": r"WM_UPDATEUISTATE",
    "accSelect": r"\baccSelect\b",
    "SetFocus": r"\bSetFocus\(",
}

LIMITATIONS = [
    "Automated UI Automation and injected keyboard input are not a screen-reader acceptance: "
    "no NVDA, Narrator or human reading pass was performed, so screen_reader_verified stays false.",
    "The audit measures what UIA and the real message path expose; it does not judge speech "
    "output, verbosity, pronunciation or reading order inside a page.",
    "The host paints page text itself and exposes no text provider; RD-02 records that as a "
    "measured finding instead of a reader judgement.",
    "Only the fixed Win32 host at the recorded source is audited; iOS, Android, GTK, sync and "
    "network features are out of scope.",
    "Keyboard transport is recorded per keystroke; modifier chords are only claimed as verified "
    "under the SendInput transport.",
]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def artifact_index(root, relative_paths):
    items = []
    for relative in sorted(set(relative_paths)):
        path = Path(root) / relative
        if not path.is_file():
            continue
        items.append({"path": relative, "bytes": path.stat().st_size, "sha256": digest(path)})
    return items


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", type=Path, required=True,
                        help="packaged EXReader directory with EXReader.exe and Reader.otf")
    parser.add_argument("--fixtures", type=Path, required=True,
                        help="book fixtures directory with Pages.pdf")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--epub", default="Sample.epub",
                        help="book inside the payload used for the reflow flow")
    parser.add_argument("--pdf", default="Pages.pdf",
                        help="fixed-page book inside the fixtures directory")
    parser.add_argument("--pdf-filter", default="Pages",
                        help="search text that narrows the shelf to the PDF")
    parser.add_argument("--comment", default="键盘审计标注")
    parser.add_argument("--source", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    parser.add_argument("--attempt", type=int, default=int(os.environ.get("GITHUB_RUN_ATTEMPT", "0") or 0))
    parser.add_argument("--repo-root", type=Path, default=HERE.parents[1])
    parser.add_argument("--keep-data", action="store_true")
    args = parser.parse_args()

    payload = args.payload.absolute()
    output = args.output.absolute()
    data_dir = output / "host-data"
    output.mkdir(parents=True, exist_ok=True)
    trace = evidence.Trace(output / evidence.TRACE_NAME)
    recorder = evidence.Recorder(trace)
    started = time.time()
    audit_completed = True
    environment = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "screen": list(w32.screen_size()),
        "dpi_aware": w32.make_dpi_aware(),
        "payload": str(payload),
        "executable": str(payload / "EXReader.exe"),
        "executable_sha256": digest(payload / "EXReader.exe")
        if (payload / "EXReader.exe").is_file() else None,
        "host_window": None,
        "uia": None,
        "keyboard": None,
        "workflow": WORKFLOW,
        "implementation_start": IMPLEMENTATION_START,
        "sdk_frozen": SDK_FROZEN,
        "product_schema": PRODUCT_SCHEMA,
    }

    if not (payload / "EXReader.exe").is_file():
        raise SystemExit("payload has no EXReader.exe: %s" % payload)

    static = evidence.static_evidence(args.repo_root, PROVIDER_PATTERNS)
    uia = uia_layer.Uia()
    environment["uia"] = {"available": uia.available, "version": uia.version,
                          "error": uia.error}
    if not uia.available:
        recorder.error("HARNESS-UIA", "keyboard",
                       "UI Automation client is available on the runner",
                       "uiautomation could not be imported: %s" % (uia.error,),
                       steps=["pip install uiautomation", "import uiautomation"])
        audit_completed = False

    host = Host(payload / "EXReader.exe", data_dir, trace=trace, workdir=payload)
    session = None
    reader = None
    try:
        host.start()
        environment["host_window"] = {
            "hwnd": hex(host.hwnd), "class": w32.class_name(host.hwnd),
            "title": w32.window_text(host.hwnd), "rect": w32.window_rect(host.hwnd),
        }
        element = uia.control(host.hwnd)
        environment["uia"]["main_window_element"] = element is not None
        if element is None:
            recorder.error("HARNESS-UIA-ELEMENT", "keyboard",
                           "UI Automation yields an element for the host window",
                           "ControlFromHandle returned no element for the real window",
                           steps=["ControlFromHandle(main window)"])
            audit_completed = False
        problems = host.verified_controls()
        if problems:
            recorder.record(
                "HARNESS-CONTROLS", "keyboard", "the launched binary is the expected host build",
                "blocking", "error",
                "every IDC_* control of examples/reader.c exists with its expected class",
                "control problems: %s" % "; ".join(problems),
                steps=["enumerate the direct children of the main window by control id"],
                element={"hwnd": hex(host.hwnd)}, reason="; ".join(problems),
                fix="audit the packaged product host built with the product catalog and metadata")
            audit_completed = False
        reader = keyboard_module.Keyboard(host.hwnd, trace=trace)
        probe = reader.ensure()
        environment["keyboard"] = probe
        if not probe.get("transport"):
            recorder.record(
                "HARNESS-KEY", "keyboard", "the keyboard reaches the host on this runner",
                "blocking", "error",
                "injected or posted key events move the host keyboard focus",
                "no transport moved focus: %r" % (probe.get("attempts"),),
                steps=["send Tab with SendInput", "if unchanged, post WM_KEYDOWN"],
                element={"hwnd": hex(host.hwnd)}, reason="no keyboard transport",
                fix="run the audit on an interactive runner session")
            audit_completed = False
        session = Session(host, reader, uia, trace, output)
        session.selection_ready = False
        host.wait_idle(timeout=180)

        phases = [
            ("launch", lambda: flows.phase_launch(session, recorder), "shelf"),
            ("import", lambda: flows.phase_import(session, recorder, str(payload / args.epub)),
             "import"),
            ("open-epub", lambda: _open_first(session, recorder), "reading"),
            ("reading", lambda: flows.phase_reading(session, recorder), "reading"),
            ("keyboard", lambda: flows.phase_keyboard(session, recorder), "keyboard"),
            ("annotation", lambda: flows.phase_annotation(session, recorder, args.comment),
             "annotation"),
            ("settings", lambda: flows.phase_settings(session, recorder), "settings"),
            ("details", lambda: flows.phase_details(session, recorder), "organize"),
            ("fixed-book", lambda: _open_fixed(session, recorder, args.fixtures, args.pdf,
                                               args.pdf_filter), "settings"),
        ]
        for label, call, scope in phases:
            try:
                call()
            except Exception as exc:
                trace.event("phase_error", {"phase": label, "error": str(exc)})
                recorder.error("HARNESS-%s" % label.upper(), scope,
                               "the %s phase runs on the real host" % label,
                               "%s: %s" % (type(exc).__name__, exc),
                               steps=[traceback.format_exc().splitlines()[-1]])
                audit_completed = False

        static_checks(session, recorder, static)
    finally:
        close_info = {}
        if host.process is not None:
            close_info = host.close(reader, timeout=60)
            environment["close"] = close_info
        environment["host_ini"] = host.read_ini()
        environment["data_dir_retained"] = bool(args.keep_data)
        trace.event("audit_finished", {"seconds": round(time.time() - started, 1)})
        trace.close()
        report = build_report(recorder, environment, static, output, args,
                              audit_completed)
        evidence.write_json(output / "report.json", report)
        print(json.dumps({
            "audit_completed": report["audit_completed"],
            "accessibility_accepted": report["accessibility_accepted"],
            "counts": report["counts"],
            "blocking": report["blocking"],
            "artifacts": len(report["artifacts"]),
        }, ensure_ascii=False, indent=2))


def _open_first(session, recorder):
    result = flows.select_and_open(session)
    session.dump("t01-shelf-loaded")
    session.shot("01-shelf-loaded")
    if not result.get("ok"):
        raise RuntimeError("the first book did not open: %r" % (result,))
    session.dump("t02-reading")


def _open_fixed(session, recorder, fixtures, pdf_name, filter_text):
    pdf = Path(fixtures) / pdf_name
    imported = flows.import_book(session, str(pdf))
    if not imported.get("ok"):
        raise RuntimeError("the fixed-page book could not be imported: %r" % (imported,))
    session.host.wait_for(lambda: len(session.list_item_names("books")) >= 2, timeout=90,
                          interval=0.25, label="shelf holds both books")
    names = flows.phase_search(session, recorder, filter_text, filter_text)
    opened = flows.select_and_open(session)
    if not opened.get("ok"):
        raise RuntimeError("the fixed-page book did not open: %r" % (opened,))
    session.dump("t04-reading-fixed")
    session.shot("04-reading-fixed")
    flows.phase_fixed(session, recorder)
    flows.clear_search(session)


def static_checks(session, recorder, static):
    """Record the two findings that only source inspection can establish."""
    provider_hits = (static.get("WM_GETOBJECT", {}).get("count", 0)
                     + static.get("UiaReturnRawElementProvider", {}).get("count", 0)
                     + static.get("IAccessible", {}).get("count", 0))
    event_hits = static.get("NotifyWinEvent", {}).get("count", 0)
    recorder.record(
        "KB-05", "keyboard", "the host implements an accessibility provider for its own widgets",
        "blocking", "gap" if provider_hits == 0 else "pass",
        "the custom page view answers WM_GETOBJECT with a UIA or MSAA provider so its text and "
        "selection are readable",
        "WM_GETOBJECT=%d, UiaReturnRawElementProvider=%d, IAccessible=%d in examples/reader.c and "
        "apps/reader/desktop; the custom EXReaderPage is served by the default proxy"
        % (static.get("WM_GETOBJECT", {}).get("count", 0),
           static.get("UiaReturnRawElementProvider", {}).get("count", 0),
           static.get("IAccessible", {}).get("count", 0)),
        steps=["git grep the host sources for accessibility provider entry points"],
        element={"source": "examples/reader.c", "class": "EXReaderPage"},
        evidence={"static": {key: value.get("count") for key, value in static.items()}},
        fix="implement WM_GETOBJECT on EXReaderPage returning a raw element provider whose "
            "Name/Text pattern follows the painted page and its selection")

    recorder.record(
        "IM-05", "import", "result changes are announced to assistive technology",
        "serious", "gap" if event_hits == 0 else "pass",
        "a status change raises an accessibility event (for example EVENT_OBJECT_NAMECHANGE on "
        "the status line) so a screen reader speaks the import result without polling",
        "NotifyWinEvent calls in the host sources=%d; the status line is a plain Static control"
        % (event_hits,),
        steps=["git grep the host sources for accessibility event notifications",
               "compare with the measured Text exposure of the status control"],
        element={"control_id": 125, "class": "Static"},
        evidence={"notify_win_event": event_hits,
                  "status_text": session.status()},
        fix="raise EVENT_OBJECT_NAMECHANGE (or a UIA Notification) from set_status/set_statusf")


def build_report(recorder, environment, static, output, args, audit_completed):
    counts = recorder.counts()
    blocking = [check["id"] for check in recorder.checks
                if check["severity"] == "blocking"
                and check["status"] in ("fail", "gap", "error")]
    errors = [check["id"] for check in recorder.checks if check["status"] == "error"]
    not_verified = [check["id"] for check in recorder.checks
                    if check["status"] == "not_verified"]
    gaps = [check["id"] for check in recorder.checks if check["status"] == "gap"]
    accepted = bool(audit_completed) and not blocking and not errors
    artifacts = []
    for key in ("screenshots", "uia_trees", "focus_crops"):
        round_trip = [str(item) for item in _collect(output, key)]
        artifacts.extend(artifact_index(output, round_trip))
    trace_path = output / evidence.TRACE_NAME
    if trace_path.is_file():
        artifacts.append({"path": evidence.TRACE_NAME, "bytes": trace_path.stat().st_size,
                          "sha256": digest(trace_path), "kind": "key_trace"})
    return {
        "schema": 1,
        "kind": "reader-a11y-windows-audit",
        "workflow": WORKFLOW,
        "source_sha": args.source,
        "run_id": str(args.run_id),
        "attempt": args.attempt,
        "implementation_start": IMPLEMENTATION_START,
        "sdk_frozen": SDK_FROZEN,
        "product_schema": PRODUCT_SCHEMA,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "audit_completed": bool(audit_completed) and not errors,
        "accessibility_accepted": accepted,
        "screen_reader_verified": False,
        "human_review_required": [
            "NVDA and Narrator pass over the same flows on a real Windows desktop",
            "reading order and speech quality of the page region once a text provider exists",
            "confidence check that no control needs a mouse",
        ],
        "counts": counts,
        "blocking": blocking,
        "gaps": gaps,
        "not_verified": not_verified,
        "errors": errors,
        "scope": SCOPE,
        "checks": recorder.checks,
        "environment": environment,
        "static_evidence": static,
        "artifacts": artifacts,
        "limitations": LIMITATIONS,
    }


def _collect(output, key):
    folder, pattern = {"screenshots": ("screenshots", "*.png"),
                       "uia_trees": ("uia", "*.json"),
                       "focus_crops": ("focus-crops", "*.png")}[key]
    base = Path(output) / folder
    if not base.is_dir():
        return []
    return sorted(str(path.relative_to(output)) for path in sorted(base.rglob(pattern))
                  if path.is_file())


if __name__ == "__main__":
    main()
