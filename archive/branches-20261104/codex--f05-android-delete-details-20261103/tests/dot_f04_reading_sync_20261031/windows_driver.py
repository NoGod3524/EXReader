#!/usr/bin/env python3
"""Actual legacy Windows product controls; no revision-consumer or database writes."""
import argparse, base64, ctypes as C, hashlib, importlib.util, json, os
from pathlib import Path
import sqlite3, sys, traceback
from ctypes import wintypes as W
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
    p.add_argument("--phase", choices=("windows-seed", "windows-peer", "windows-return", "windows-import-only"), required=True)
    p.add_argument("--producer-receipt", type=Path)
    args = p.parse_args()
    assert (args.phase in ("windows-seed", "windows-import-only")) == (args.previous is None)
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    rec = module("f04_windows_records", "tests/reader_windows_records/check_ui.py")
    account = module("f04_windows_account", "tests/reader_windows_account/check_account_ui.py")
    rec.U.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
    class Device(rec.RecordsApp, account.Device):
        def menu_command(self, identifier):
            assert identifier in (137, 210, 107), "unapproved menu entry"
            self.wait_idle(); self.focus()
            assert rec.U.GetForegroundWindow() == self.window and rec.U.IsWindowEnabled(self.window), "menu owner unavailable"
            pid = W.DWORD(); rec.U.GetWindowThreadProcessId(self.window, C.byref(pid))
            assert pid.value == self.process.pid, "menu wrong process"
            rec.U.GetMenu.argtypes = [W.HWND]; rec.U.GetMenu.restype = W.HANDLE
            rec.U.GetSubMenu.argtypes = [W.HANDLE, C.c_int]; rec.U.GetSubMenu.restype = W.HANDLE
            rec.U.GetMenuItemCount.argtypes = [W.HANDLE]; rec.U.GetMenuItemCount.restype = C.c_int
            rec.U.GetMenuItemID.argtypes = [W.HANDLE, C.c_int]; rec.U.GetMenuItemID.restype = W.UINT
            rec.U.GetMenuState.argtypes = [W.HANDLE, W.UINT, W.UINT]; rec.U.GetMenuState.restype = W.UINT
            found = []
            def visit(menu):
                for index in range(rec.U.GetMenuItemCount(menu)):
                    child = rec.U.GetSubMenu(menu, index)
                    if child: visit(child)
                    elif rec.U.GetMenuItemID(menu, index) == identifier:
                        found.append(rec.U.GetMenuState(menu, index, 0x400))
            visit(rec.U.GetMenu(self.window))
            assert len(found) == 1 and found[0] != 0xFFFFFFFF and not (found[0] & 3), "menu missing or disabled"
            rec.send(self.window, 0x111, identifier, 0)
        def open_account(self):
            self.menu_command(137)
            dialog = self.account_dialog(); self.settle(dialog)
            return dialog
        def close(self):
            try:
                if self.process.poll() is None:
                    assert rec.U.PostMessageW(self.window, 0x10, 0, 0), "normal close request refused"
                    self.process.wait(timeout=30)
                assert self.process.returncode == 0, "normal close exit not zero"
            except BaseException:
                if self.process.poll() is None:
                    self.process.kill(); self.process.wait(timeout=10)
                raise
            finally:
                self.log.close()
        def import_file(self, path):
            self.wait_initial_shelf(); self.wait_idle()
            assert rec.send(self.control("books"), 0x18B) == 0, "seed profile not empty"
            self.wait(lambda: rec.U.SetForegroundWindow(self.window) or rec.U.GetForegroundWindow() == self.window)
            assert rec.U.GetForegroundWindow() == self.window, "Import app not foreground"
            rec.M.set_text(self.control("path"), str(path))
            assert rec.text(self.control("path")) == str(path), "Import path mismatch"
            button = self.control("import")
            assert rec.U.IsWindowVisible(button) and rec.U.IsWindowEnabled(button), "Import not available"
            pid = W.DWORD(); rec.U.GetWindowThreadProcessId(button, C.byref(pid))
            assert pid.value == self.process.pid, "Import wrong process"
            rectangle = W.RECT()
            rec.U.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
            assert rec.U.GetWindowRect(button, C.byref(rectangle)), "Import rectangle"
            x, y = (rectangle.left + rectangle.right) // 2, (rectangle.top + rectangle.bottom) // 2
            rec.U.WindowFromPoint.argtypes = [W.POINT]; rec.U.WindowFromPoint.restype = W.HWND
            assert rec.U.WindowFromPoint(W.POINT(x, y)) == button, "Import hit occluded"
            class Mouse(C.Structure):
                _fields_ = [("dx", W.LONG), ("dy", W.LONG), ("mouseData", W.DWORD),
                            ("dwFlags", W.DWORD), ("time", W.DWORD), ("extra", C.c_size_t)]
            class Payload(C.Union):
                _fields_ = [("mi", Mouse)]
            class Input(C.Structure):
                _fields_ = [("type", W.DWORD), ("data", Payload)]
            rec.U.SendInput.argtypes = [W.UINT, C.POINTER(Input), C.c_int]
            rec.U.SendInput.restype = W.UINT
            assert rec.U.SetCursorPos(x, y), "Import cursor move failed"
            assert rec.U.WindowFromPoint(W.POINT(x, y)) == button and rec.U.GetForegroundWindow() == self.window, "Import target changed"
            events = (Input * 2)()
            events[0].data.mi.dwFlags = 0x0002
            events[1].data.mi.dwFlags = 0x0004
            sent = rec.U.SendInput(2, events, C.sizeof(Input))
            report["import_input"] = {"method": "SendInput", "events_sent": sent, "dispatches": 1}
            assert sent == 2, "Import physical input refused; not retried"
            # Compact host always opens the real system picker, ignoring hidden path.
            rec.U.GetParent.argtypes = [W.HWND]; rec.U.GetParent.restype = W.HWND
            rec.U.GetDlgCtrlID.argtypes = [W.HWND]; rec.U.GetDlgCtrlID.restype = C.c_int
            rec.U.GetWindow.argtypes = [W.HWND, W.UINT]; rec.U.GetWindow.restype = W.HWND
            rec.U.EnumChildWindows.argtypes = [W.HWND, rec.M.ENUM, W.LPARAM]
            def classname(window):
                name = C.create_unicode_buffer(100); rec.U.GetClassNameW(window, name, 100)
                return name.value
            def owned_picker():
                candidates = []
                @rec.M.ENUM
                def visit(window, unused):
                    pid = W.DWORD(); rec.U.GetWindowThreadProcessId(window, C.byref(pid))
                    if pid.value == self.process.pid and window != self.window and rec.U.IsWindowVisible(window) and classname(window) == "#32770" and rec.U.GetWindow(window, 4) == self.window:
                        candidates.append(window)
                    return True
                rec.U.EnumWindows(visit, 0)
                assert len(candidates) <= 1, "ambiguous owned picker"
                return candidates[0] if candidates else None
            dialog = self.wait(owned_picker, timeout=30)
            def filename_control():
                found = []
                @rec.M.ENUM
                def child(window, unused):
                    if classname(window) == "Edit" and rec.U.IsWindowVisible(window) and rec.U.IsWindowEnabled(window):
                        parent = rec.U.GetParent(window)
                        matched = rec.U.GetDlgCtrlID(window) == 1001 and classname(parent) == "ComboBox" and classname(rec.U.GetParent(parent)) == "FloatNotifySink"
                        ancestor = window
                        while ancestor and ancestor != dialog:
                            matched |= rec.U.GetDlgCtrlID(ancestor) in (1148, 1152)
                            ancestor = rec.U.GetParent(ancestor)
                        if matched: found.append(window)
                    return True
                rec.U.EnumChildWindows(dialog, child, 0)
                assert len(found) <= 1, "ambiguous filename control"
                return found[0] if found else None
            filename = self.wait(filename_control, timeout=30)
            rec.M.set_text(filename, str(path))
            assert rec.text(filename) == str(path), "system picker path mismatch"
            accept = rec.U.GetDlgItem(dialog, 1)
            assert accept and rec.U.IsWindowVisible(accept) and rec.U.IsWindowEnabled(accept), "picker accept unavailable"
            # One native acceptance event; no retry loop from the older recipe.
            assert rec.U.PostMessageW(accept, 0xF5, 0, 0), "picker accept not posted"
            self.wait(lambda: not rec.U.IsWindow(dialog), timeout=30)
            report["import_input"]["system_picker_accepted_once"] = True
            # No second import click and no timeout suppression.
            self.wait(lambda: rec.send(self.control("books"), 0x18B) == 1, timeout=120)
            self.wait_idle()
            assert self.row(args.title) == 0 and rec.send(self.control("books"), 0x18B) == 1, "Import target row mismatch"
    app = dav = trust = user = password = None
    phase = 'launch'
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
        app.wait_idle(); app.menu_command(rec.BUTTON)
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
        if args.phase == "windows-import-only":
            assert args.producer_receipt is not None
            producer = json.loads(args.producer_receipt.read_text())
            report["product_producer"] = producer
            report["scope"] = "fixed historical Windows import path only"
            report["same_current_source_runtime"] = False
            app = Device(args.candidate.resolve(), args.font.resolve(), out / "profile")
            phase = "import"
            app.import_file(args.original.resolve())
            check("fresh_library_single_import", rec.send(app.control("books"), 0x18B) == 1)
            app.open(args.title); app.wait_idle()
            app.wait(lambda: frame() != "未打开书籍" and bool(frame()), timeout=60)
            page = rec.U.GetDlgItem(app.window, 123)
            assert rec.U.IsWindowVisible(page) and rec.U.GetForegroundWindow() == app.window
            bounds = W.RECT(); assert rec.U.GetWindowRect(page, C.byref(bounds))
            assert bounds.right - bounds.left > 8 and bounds.bottom - bounds.top > 8
            from PIL import ImageGrab
            picture = ImageGrab.grab(bbox=(bounds.left + 3, bounds.top + 3, bounds.right - 3, bounds.bottom - 3))
            extrema = picture.convert("RGB").getextrema()
            check("opened_page_nonuniform_pixels", any(low != high for low, high in extrema))
            picture.save(out / "opened-page.png")
            report["opened_page"] = {"label": frame(), "extrema": extrema}
            assert rec.U.PostMessageW(app.window, 0x10, 0, 0), "normal close request failed"
            code = app.process.wait(timeout=30)
            check("normal_close_zero", code == 0)
            report["passed"] = True
            report["program"] = {"sha256": hashlib.sha256(args.candidate.read_bytes()).hexdigest(),
                                 "bytes": args.candidate.stat().st_size}
            return
        dav, user, password = start(out, previous=args.previous)
        trust = trust_desktop(out / "cert.pem", "f04-windows")
        app = Device(args.candidate.resolve(), args.font.resolve(), out / "profile")
        app.wait_initial_shelf(); app.wait_idle()
        # Only the seed imports locally. A receiver starts empty, otherwise
        # staging a local bootstrap could create a competing book root.
        if args.phase == "windows-seed":
            phase = "import"
            app.import_file(args.original.resolve()); app.wait_idle()
        phase = "account-and-records"
        d = app.open_account()
        app.fill(d, dav.base + "/dav/", user, password, False)
        app.apply(d, "仅本次会话"); app.close_account(d)
        if args.previous:
            sync()  # Windows final sync includes real receive/import/mapping.
            app.wait(lambda: app.has_row(args.title), timeout=120)
        app.open(args.title); app.wait_idle()
        if args.phase == "windows-seed":
            # Fixed Alice EPUB opens on an image cover. Use real page actions,
            # as the retained Apple producer does, before capturing a range.
            for _ in range(3):
                previous_page = frame(); app.click("next"); app.wait_idle()
                app.wait(lambda: frame() != previous_page)
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
            app.menu_command(107); app.wait_idle()
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
        (out / "program.bin").write_bytes(args.candidate.read_bytes())
        report["passed"] = True
        save(dav, out, args.phase, report); dav = None
    except BaseException as error:
        report["passed"] = False
        report["failure_phase"] = phase
        report["error_type"] = type(error).__name__
        diagnostic = ROOT / "build/f04-diagnostics/windows"
        diagnostic.mkdir(parents=True, exist_ok=True)
        try:
            from run import diagnostic_text
            secrets = [user, password]
            if user is not None and password is not None:
                secrets.append(base64.b64encode((user + ":" + password).encode()).decode())
            cleaned_exception = diagnostic_text(traceback.format_exc(), secrets)
            print(cleaned_exception, flush=True)
            (diagnostic / "exception.txt").write_text(cleaned_exception, encoding="utf-8")
            if app:
                observed = {"process_id": app.process.pid, "exit_code": app.process.poll(),
                            "window_exists": bool(rec.U.IsWindow(app.window)), "phase": phase}
                try:
                    observed["status"] = diagnostic_text(app.status(), secrets)
                except Exception as observation_error:
                    observed["status_error"] = type(observation_error).__name__
                windows = []
                @rec.M.ENUM
                def visit(window, unused):
                    pid = W.DWORD(); rec.U.GetWindowThreadProcessId(window, C.byref(pid))
                    if pid.value == app.process.pid and rec.U.IsWindowVisible(window):
                        name = C.create_unicode_buffer(100); rec.U.GetClassNameW(window, name, 100)
                        windows.append({"class": name.value, "main": window == app.window,
                                        "foreground": window == rec.U.GetForegroundWindow(),
                                        "enabled": bool(rec.U.IsWindowEnabled(window))})
                    return True
                rec.U.EnumWindows(visit, 0)
                observed["owned_visible_windows"] = windows
                print("F04 DIAGNOSTIC WINDOW " + json.dumps(observed), flush=True)
                (diagnostic / "window.json").write_text(json.dumps(observed, indent=2), encoding="utf-8")
                log = out / "profile/application.log"
                if log.is_file():
                    (diagnostic / "application.txt").write_text(diagnostic_text(log.read_text(encoding="utf-8"), secrets), encoding="utf-8")
                # Capture only before credentials ever enter the UI. Never desktop/account screenshots.
                if phase == "import" and rec.U.IsWindow(app.window) and rec.U.GetForegroundWindow() == app.window:
                    from PIL import ImageGrab
                    rect = W.RECT()
                    if rec.U.GetWindowRect(app.window, C.byref(rect)):
                        ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom)).save(diagnostic / "import-window.png")
        except Exception as diagnostic_error:
            # Do not fall back to copying unsanitized bytes.
            (diagnostic / "diagnostic-refused.json").write_text(json.dumps({"error_type": type(diagnostic_error).__name__}))
        raise
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
