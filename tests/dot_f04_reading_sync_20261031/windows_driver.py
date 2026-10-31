#!/usr/bin/env python3
"""Actual legacy Windows product controls; no revision-consumer or database writes."""
import argparse, base64, ctypes as C, hashlib, importlib.util, json, os
from pathlib import Path
import sqlite3, sys
ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from relay import start, save, identity, trust_desktop, untrust_desktop, retained_rows, finish_cleanup

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result

def main():
    assert os.environ.get("GITHUB_ACTIONS") == "true" and os.name == "nt"
    p = argparse.ArgumentParser()
    for name in ("candidate", "font", "original", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--previous", type=Path)
    p.add_argument("--title", required=True)
    p.add_argument("--incoming-prefix", default="F04_APPLE")
    p.add_argument("--phase", choices=("windows-seed", "windows-peer", "windows-return"), required=True)
    args = p.parse_args()
    assert (args.phase == "windows-seed") == (args.previous is None)
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    rec = module("f04_windows_records", "tests/reader_windows_records/check_ui.py")
    account = module("f04_windows_account", "tests/reader_windows_account/check_account_ui.py")
    class Device(rec.RecordsApp, account.Device):
        pass
    app = dav = trust = None
    report = dict(identity(), platform="windows", sdk_version="3.42.0",
                  f04_stage="six-host-reading-preparation-v2", passed=False,
                  checks=[], navigations=[], F04_accepted=False)
    original = args.original.read_bytes()
    contract = json.loads((HERE / "contract.json").read_text())
    assert hashlib.sha256(original).hexdigest() == contract["original"]["sha256"]
    report.update(original_sha256=hashlib.sha256(original).hexdigest(), original_bytes=len(original),
                  book_identity="epub:" + hashlib.sha256(original).hexdigest())
    def check(name, condition):
        assert condition, name
        report["checks"].append(name)
    def settle(d):
        app.wait(lambda: not rec.U.IsWindowEnabled(rec.U.GetDlgItem(d, rec.CANCEL)), timeout=90)
        app.wait_idle()
    def show():
        app.wait_idle(); rec.send(rec.U.GetDlgItem(app.window, rec.BUTTON), 0xF5)
        d = app.dialog(); settle(d); return d
    def press(d, control):
        rec.send(rec.U.GetDlgItem(d, control), 0xF5); settle(d)
        return rec.text(rec.U.GetDlgItem(d, rec.MESSAGE))
    def labels(d):
        box = rec.U.GetDlgItem(d, rec.ROWS); result = []
        for i in range(rec.send(box, 0x18B)):
            n = rec.send(box, 0x18A, i); buf = C.create_unicode_buffer(n + 1)
            rec.send(box, 0x189, i, C.addressof(buf)); result.append(buf.value)
        return result
    def choose(d, marker):
        matches = [i for i, value in enumerate(labels(d)) if marker in value]
        assert len(matches) == 1, (marker, labels(d))
        box = rec.U.GetDlgItem(d, rec.ROWS)
        rec.send(box, 0x186, matches[0]); rec.send(d, 0x111, (1 << 16) | rec.ROWS, box)
    def close(d):
        rec.send(rec.U.GetDlgItem(d, rec.CLOSE), 0xF5)
        app.wait(lambda: not rec.U.IsWindow(d)); app.wait_idle()
    def body(d, value):
        rec.M.set_text(rec.U.GetDlgItem(d, rec.BODY), value)
    def sync():
        d = app.open_account(); app.run_sync(d); app.close_account(d)
    def frame():
        return rec.text(rec.U.GetDlgItem(app.window, 124))
    def rows():
        return retained_rows(Path(str(app.db) + ".product.sqlite"))
    try:
        dav, user, password = start(out, previous=args.previous)
        trust = trust_desktop(out / "cert.pem", "f04-windows")
        app = Device(args.candidate.resolve(), args.font.resolve(), out / "profile")
        app.wait_initial_shelf(); app.wait_idle()
        # Only the seed imports locally. A receiver starts empty, otherwise
        # staging a local bootstrap could create a competing book root.
        if args.phase == "windows-seed":
            app.import_file(args.original.resolve()); app.wait_idle()
        d = app.open_account()
        app.fill(d, dav.base + "/dav/", user, password, False)
        app.apply(d, "仅本次会话"); app.close_account(d)
        if args.previous:
            sync()  # Windows final sync includes real receive/import/mapping.
            app.wait(lambda: app.has_row(args.title), timeout=120)
        app.open(args.title); app.wait_idle()
        before = frame()
        sync()
        check("remote_sync_does_not_move_active_reader", frame() == before)
        received = rows(); report["incoming"] = received
        if args.previous:
            d = show()
            box = rec.U.GetDlgItem(d, rec.ROWS)
            rec.send(box, 0x186, 0); rec.send(d, 0x111, (1 << 16) | rec.ROWS, box)
            message = press(d, rec.OPEN)
            check("public_found_progress", "独立原书与当前绘图文档" in message)
            report["progress_navigation"] = {"native_message": message, "native_status": app.status(), "page_label": frame()}
            for suffix in ("BOOKMARK", "NOTE"):
                marker = args.incoming_prefix + "_" + suffix
                choose(d, marker)
                message = press(d, rec.OPEN)
                check("public_found_" + suffix.lower(), "独立原书与当前绘图文档" in message)
                report["navigations"].append({"marker": marker, "native_message": message,
                                               "native_status": app.status()})
            close(d)
        if args.phase != "windows-return":
            before = frame()
            d = show(); press(d, rec.PROGRESS)
            body(d, "F04_WINDOWS_BOOKMARK"); press(d, rec.BOOKMARK); close(d)
            app.click("select"); app.wait_idle()
            d = show(); body(d, "F04_WINDOWS_NOTE"); press(d, rec.HIGHLIGHT); close(d)
            check("record_creation_does_not_navigate", frame() == before)
            sync()
        outgoing = rows(); report["outgoing"] = outgoing
        for row in received:
            match = [r for r in outgoing if r["revision_id"] == row["revision_id"]]
            check("retained_" + row["revision_id"], match == [row])
        check("native_authenticated_transport", bool(dav.requests) and all(r["authenticated"] for r in dav.requests))
        if args.phase != "windows-return":
            check("native_client_put", any(r["method"] == "PUT" and "/revisions/" in r["path"] for r in dav.requests))
        report["program"] = {"sha256": hashlib.sha256(args.candidate.read_bytes()).hexdigest(),
                             "bytes": args.candidate.stat().st_size}
        report["passed"] = True
        save(dav, out, args.phase, report); dav = None
    finally:
        actions = []
        if app: actions.append(("close-actual-app", app.close))
        if dav:
            actions.extend([
                ("save-requests", lambda: (out / "requests.json").write_text(json.dumps(dav.requests, indent=2))),
                ("stop-fixture", dav.server.shutdown),
                ("close-fixture", dav.server.server_close)])
        if trust: actions.append(("remove-fixture-trust", lambda: untrust_desktop(trust)))
        actions.append(("remove-fixture-key", lambda: (out / "key.pem").unlink(missing_ok=True)))
        finish_cleanup(actions, report, out / "result.json")
if __name__ == "__main__": main()
