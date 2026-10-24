# SPDX-License-Identifier: MIT
"""Process control and control identification for the real Win32 host.

The host is launched exactly as a user launches it (no driver script, no
injected commands). Controls are located by dialog control id plus window class,
which is the identity the product's own source assigns, and every id is checked
against the expected class so a different build cannot be audited silently.
"""
from __future__ import annotations

import configparser
import subprocess
import time
from pathlib import Path

import w32

# IDC_* values from examples/reader.c: an enum starting at 100 in creation order.
CONTROLS = {
    "import_label": 100, "import_edit": 101, "import_button": 102, "open_button": 103,
    "delete_button": 104, "prev": 105, "next": 106, "select_all": 107, "copy_quote": 108,
    "add_note": 109, "update_note": 110, "delete_note": 111, "jump_note": 112,
    "font_dec": 113, "font_inc": 114, "zoom_dec": 115, "zoom_inc": 116, "cancel": 117,
    "shelf_label": 118, "books": 119, "notes_label": 120, "notes": 121, "note_edit": 122,
    "page": 123, "page_label": 124, "status": 125, "shelf_search": 126, "shelf_refresh": 127,
    "metadata_button": 128, "metadata_title": 129, "metadata_author": 130,
    "metadata_favorite": 131, "metadata_save": 132, "metadata_cancel": 133,
    "metadata_retry": 134, "metadata_discard": 135, "metadata_message": 136,
}
IDS = {value: name for name, value in CONTROLS.items()}

# Control creation order in examples/reader.c, which is also the z-order the
# dialog manager walks for Tab. It differs from id order because the product
# catalog controls (126-128) are created right after the book list.
TAB_ORDER = [
    "import_label", "import_edit", "import_button", "open_button", "delete_button",
    "prev", "next", "select_all", "copy_quote", "add_note", "update_note", "delete_note",
    "jump_note", "font_dec", "font_inc", "zoom_dec", "zoom_inc", "cancel",
    "shelf_label", "books", "shelf_search", "shelf_refresh", "metadata_button",
    "notes_label", "notes", "note_edit", "page", "page_label", "status",
]

EXPECTED_CLASS = {
    "import_label": "static", "shelf_label": "static", "notes_label": "static",
    "page_label": "static", "status": "static", "metadata_message": "static",
    "import_edit": "edit", "shelf_search": "edit", "note_edit": "edit",
    "metadata_title": "edit", "metadata_author": "edit",
    "books": "listbox", "notes": "listbox",
    "page": "exreaderpage",
    "metadata_favorite": "button",
}

MAIN_CLASS = "EXReaderHost"
DIALOG_CLASS = "#32770"
METADATA_CONTROLS = ("metadata_button", "metadata_title", "metadata_author",
                     "metadata_favorite", "metadata_save", "metadata_cancel",
                     "metadata_retry", "metadata_discard", "metadata_message")


class HostStartError(RuntimeError):
    pass


class Host(object):
    def __init__(self, exe, data_dir, trace=None, workdir=None, timeout=120):
        self.exe = Path(exe)
        self.data_dir = Path(data_dir)
        self.workdir = Path(workdir) if workdir else self.exe.parent
        self.trace = trace
        self.timeout = timeout
        self.process = None
        self.hwnd = 0
        self.pid = 0
        self._children = {}
        self.log_path = None
        self.ini_path = self.data_dir / "host.ini"
        self.started_utc = None

    # -- lifecycle ------------------------------------------------------------
    def start(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.data_dir / "host-stdout.log"
        arguments = [str(self.exe), "--data", str(self.data_dir)]
        self.started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self.log_path.open("wb") as log:
            self.process = subprocess.Popen(
                arguments, cwd=str(self.workdir), stdout=log, stderr=subprocess.STDOUT)
        self.pid = int(self.process.pid)
        self.hwnd = self._wait_window(self.timeout)
        if not self.hwnd:
            raise HostStartError("host window never appeared (pid %d)" % self.pid)
        w32.bring_to_front(self.hwnd)
        self.refresh()
        return self.hwnd

    def _wait_window(self, timeout):
        deadline = time.time() + timeout
        while time.time() < deadline:
            for hwnd in w32.top_windows():
                tid, pid = w32.thread_id(hwnd)
                if pid != self.pid or not w32.user32.IsWindowVisible(hwnd):
                    continue
                klass = w32.class_name(hwnd).lower()
                if klass == DIALOG_CLASS:
                    continue
                return hwnd
            if self.process.poll() is not None:
                return 0
            time.sleep(0.2)
        return 0

    def alive(self):
        return self.process is not None and self.process.poll() is None

    def close(self, keyboard=None, timeout=45):
        result = {"requested": "alt+f4", "graceful": False, "exit_code": None}
        if not self.alive():
            result["graceful"] = True
            result["exit_code"] = self.process.poll() if self.process else None
            return result
        w32.bring_to_front(self.hwnd)
        if keyboard is not None and keyboard.transport == "sendinput":
            keyboard.press("f4", ("alt",), note="close the host like a user")
        else:
            w32.user32.PostMessageW(self.hwnd, w32.WM_CLOSE, 0, 0)
            result["requested"] = "wm_close"
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.process.poll() is not None:
                result["graceful"] = True
                result["exit_code"] = int(self.process.returncode)
                return result
            time.sleep(0.2)
        self.process.kill()
        try:
            self.process.wait(timeout=15)
        except Exception:
            pass
        result["exit_code"] = int(self.process.returncode if self.process.returncode is not None else -1)
        result["killed"] = True
        return result

    # -- controls -------------------------------------------------------------
    def refresh(self):
        self._children = {}
        if not self.hwnd or not w32.user32.IsWindow(self.hwnd):
            return self._children
        for hwnd in w32.direct_children(self.hwnd):
            identifier = w32.ctrl_id(hwnd)
            if identifier:
                self._children[identifier] = hwnd
        return self._children

    def control(self, name, refresh=False):
        if refresh:
            self.refresh()
        identifier = CONTROLS.get(name)
        if identifier is None:
            raise KeyError("unknown control %r" % (name,))
        hwnd = self._children.get(identifier, 0)
        if hwnd and not w32.user32.IsWindow(hwnd):
            self.refresh()
            hwnd = self._children.get(identifier, 0)
        return hwnd

    def describe_control(self, name):
        hwnd = self.control(name)
        if not hwnd:
            return {"id": CONTROLS.get(name), "name": name, "present": False}
        return {
            "id": CONTROLS.get(name),
            "name": name,
            "present": True,
            "hwnd": hwnd,
            "class": w32.class_name(hwnd),
            "text": w32.window_text(hwnd),
            "enabled": bool(w32.user32.IsWindowEnabled(hwnd)),
            "visible": bool(w32.user32.IsWindowVisible(hwnd)),
            "tabstop": bool(w32.has_style(hwnd, w32.WS_TABSTOP)),
            "rect": w32.window_rect(hwnd),
        }

    def verified_controls(self):
        """Require every main-window control of the expected build to exist."""
        self.refresh()
        problems = []
        for name, identifier in sorted(CONTROLS.items(), key=lambda item: item[1]):
            if name in METADATA_CONTROLS and name != "metadata_button":
                continue  # created with the details dialog, checked there
            hwnd = self._children.get(identifier, 0)
            if not hwnd:
                problems.append("%s (id %d) is missing" % (name, identifier))
                continue
            expected = EXPECTED_CLASS.get(name)
            if expected and w32.class_name(hwnd).lower() != expected:
                problems.append("%s (id %d) has class %r, expected %r"
                                % (name, identifier, w32.class_name(hwnd), expected))
        return problems

    def verified_dialog_controls(self, dialog):
        """Require the details-dialog controls of the expected build to exist."""
        found = self.dialog_controls(dialog)
        problems = []
        for name in ("metadata_title", "metadata_author", "metadata_favorite",
                     "metadata_save", "metadata_cancel", "metadata_message"):
            identifier = CONTROLS[name]
            if identifier not in found:
                problems.append("%s (id %d) is missing from the dialog"
                                % (name, identifier))
        return problems

    def text(self, name):
        hwnd = self.control(name)
        return w32.window_text(hwnd) if hwnd else ""

    def status(self):
        return self.text("status")

    def page_label(self):
        return self.text("page_label")

    def enabled(self, name):
        hwnd = self.control(name)
        return bool(hwnd) and bool(w32.user32.IsWindowEnabled(hwnd))

    def list_text(self, name):
        """Item strings of a listbox, read from the control (not accessibility)."""
        hwnd = self.control(name)
        if not hwnd:
            return []
        count = int(w32.user32.SendMessageW(hwnd, 0x018B, 0, 0))  # LB_GETCOUNT
        if count <= 0:
            return []
        items = []
        for index in range(count):
            length = int(w32.user32.SendMessageW(hwnd, 0x018A, index, 0))  # LB_GETTEXTLEN
            if length < 0:
                continue
            buffer = w32.ctypes.create_unicode_buffer(length + 2)
            w32.user32.SendMessageW(hwnd, 0x0189, index,  # LB_GETTEXT
                                    w32.ctypes.cast(buffer, w32.ctypes.c_void_p).value or 0)
            items.append(buffer.value)
        return items

    # -- dialog ---------------------------------------------------------------
    def dialog_window(self):
        """The host creates its details/recovery dialog as an owned #32770 window."""
        for hwnd in w32.top_windows():
            _tid, pid = w32.thread_id(hwnd)
            if pid != self.pid:
                continue
            if w32.class_name(hwnd).lower() != DIALOG_CLASS:
                continue
            return hwnd
        return None

    def dialog_controls(self, dialog):
        found = {}
        for hwnd in w32.direct_children(dialog):
            identifier = w32.ctrl_id(hwnd)
            if identifier:
                found[identifier] = hwnd
        return found

    # -- waiting --------------------------------------------------------------
    def wait_for(self, predicate, timeout=60, interval=0.15, label=""):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            try:
                last = predicate()
            except Exception as exc:
                last = None
                self.log("wait_error", {"label": label, "error": str(exc)})
            if last:
                if self.trace is not None:
                    self.trace.event("wait", {"label": label, "ok": True})
                return last
            time.sleep(interval)
        if self.trace is not None:
            self.trace.event("wait", {"label": label, "ok": False, "timeout": timeout})
        return None

    def wait_idle(self, timeout=120):
        """Wait until the host is not running a job and the status text is stable."""

        def stable():
            refresh = self.control("shelf_refresh")
            if not refresh or not w32.user32.IsWindowEnabled(refresh):
                return False
            first = self.status()
            time.sleep(0.45)
            second = self.status()
            return first == second and bool(refresh)

        return self.wait_for(stable, timeout=timeout, interval=0.2, label="idle")

    def wait_enabled(self, name, timeout=60):
        return self.wait_for(lambda: self.enabled(name), timeout=timeout, interval=0.2,
                             label="enabled:%s" % name)

    # -- files ----------------------------------------------------------------
    def read_ini(self):
        if not self.ini_path.is_file():
            return None
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        try:
            parser.read_string(self.ini_path.read_text(encoding="utf-8", errors="replace"))
        except Exception as exc:
            return {"error": str(exc), "raw": self.ini_path.read_text(
                encoding="utf-8", errors="replace")[:2000]}
        return {section: dict(parser.items(section)) for section in parser.sections()}

    def log(self, kind, payload):
        if self.trace is not None:
            self.trace.event(kind, payload)
