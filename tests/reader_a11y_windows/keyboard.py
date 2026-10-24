# SPDX-License-Identifier: MIT
"""Real keyboard input and focus introspection for the audit.

The preferred transport is SendInput, which goes through the same input path a
user's keyboard uses (hardware input queue -> focused window -> message loop ->
IsDialogMessage). When a runner session cannot deliver injected input, the
module falls back to posted WM_KEY* messages, which still exercise the host's
keyboard handlers but bypass the input queue. The transport used for every
keystroke is recorded in the trace, and modifier chords are never claimed as
verified under the fallback transport.
"""
from __future__ import annotations

import time

import w32

MODIFIERS = {
    "shift": w32.VK_SHIFT,
    "ctrl": w32.VK_CONTROL,
    "alt": w32.VK_MENU,
}

KEYS = {
    "backspace": w32.VK_BACK,
    "tab": w32.VK_TAB,
    "enter": w32.VK_RETURN,
    "escape": w32.VK_ESCAPE,
    "space": w32.VK_SPACE,
    "home": w32.VK_HOME,
    "end": w32.VK_END,
    "left": w32.VK_LEFT,
    "right": w32.VK_RIGHT,
    "up": w32.VK_UP,
    "down": w32.VK_DOWN,
    "prior": w32.VK_PRIOR,
    "next": w32.VK_NEXT,
    "f4": w32.VK_F4,
}


class Keyboard(object):
    def __init__(self, hwnd, trace=None, delay=0.05):
        self.hwnd = hwnd
        self.trace = trace
        self.delay = delay
        self.transport = None
        self.probe = {}
        self._thread = 0
        self._pid = 0
        self._last_dialog = -1
        self._foreground_failures = 0
        self._foreground_give_up_until = 0.0
        try:
            self._thread, self._pid = w32.thread_id(hwnd)
        except Exception:
            self._thread = 0

    # -- readiness ------------------------------------------------------------
    def note_dialog(self):
        """Record every appearance or disappearance of a host message/dialog window."""
        current = 0
        try:
            for hwnd in w32.top_windows():
                _tid, pid = w32.thread_id(hwnd)
                if pid != self._pid:
                    continue
                if w32.class_name(hwnd).lower() != "#32770":
                    continue
                current = hwnd
                break
        except Exception:
            return None
        if current != self._last_dialog:
            self._last_dialog = current
            self._log("host_dialog", {"hwnd": hex(current) if current else None,
                                      "title": w32.window_text(current) if current else None})
        return current

    def ready(self):
        """Keep the audited window in the foreground so real input reaches it.

        Retries are bounded: a runner session without an interactive desktop must
        not turn every keystroke into a foreground fight.
        """
        if not self.hwnd:
            return False
        current = w32.foreground()
        if current and int(w32.thread_id(current)[1]) == int(self._pid):
            # The host's own dialog may hold the foreground; that is not a loss.
            self.note_dialog()
            return True
        if current != self.hwnd:
            now = time.time()
            if now >= self._foreground_give_up_until:
                brought = w32.bring_to_front(self.hwnd)
                self._log("foreground", {"hwnd": hex(self.hwnd), "brought": brought,
                                         "foreground": hex(w32.foreground())})
                if brought:
                    self._foreground_failures = 0
                else:
                    self._foreground_failures += 1
                    if self._foreground_failures >= 2:
                        self._foreground_give_up_until = now + 30
                        self._log("foreground_unavailable",
                                  {"hwnd": hex(self.hwnd),
                                   "foreground": hex(w32.foreground()),
                                   "pause_seconds": 30})
        self.note_dialog()
        return True

    # -- focus ----------------------------------------------------------------
    def focus(self):
        """HWND that the host UI thread currently gives keyboard focus to."""
        try:
            info = w32.gui_thread_info(self._thread)
        except Exception:
            info = None
        if not info:
            return 0
        return info["focus"]

    def focus_state(self):
        try:
            return w32.gui_thread_info(self._thread) or {}
        except Exception:
            return {}

    # -- transport ------------------------------------------------------------
    def ensure(self):
        """Pick a working transport and record the probe evidence."""
        host_foreground = w32.bring_to_front(self.hwnd)
        before = self.focus()
        attempts = []
        for transport in ("sendinput", "postmessage"):
            self.transport = transport
            self._press_raw(w32.VK_TAB)
            time.sleep(0.3)
            after = self.focus()
            moved = after != before
            attempts.append({"transport": transport, "focus_before": before,
                             "focus_after": after, "focus_moved": moved})
            if moved:
                self.probe = {
                    "host_foreground": host_foreground,
                    "foreground_window": w32.foreground(),
                    "interactive_desktop": bool(w32.foreground()),
                    "thread": self._thread,
                    "attempts": attempts,
                    "transport": transport,
                    "modifier_chords_trustworthy": transport == "sendinput",
                }
                self._log("transport_selected", {"transport": transport,
                                                 "focus_before": before,
                                                 "focus_after": after})
                return self.probe
        self.transport = None
        self.probe = {
            "host_foreground": host_foreground,
            "foreground_window": w32.foreground(),
            "interactive_desktop": bool(w32.foreground()),
            "thread": self._thread,
            "attempts": attempts,
            "transport": None,
            "modifier_chords_trustworthy": False,
        }
        self._log("transport_failed", self.probe)
        return self.probe

    def _log(self, kind, payload):
        if self.trace is not None:
            self.trace.event(kind, payload)

    # -- key sending ----------------------------------------------------------
    def _press_raw(self, vk, modifiers=()):
        if self.transport == "sendinput":
            for name in modifiers:
                w32.send_key(MODIFIERS[name])
            w32.send_key(vk)
            time.sleep(0.02)
            w32.send_key(vk, up=True)
            for name in reversed(modifiers):
                w32.send_key(MODIFIERS[name], up=True)
            return True
        if self.transport == "postmessage":
            target = self.focus() or self.hwnd
            w32.post_key(target, vk)
            time.sleep(0.02)
            w32.post_key(target, vk, up=True)
            return True
        return False

    def press(self, key, modifiers=(), note=None):
        """Press one key (by name or virtual-key code) and record the step."""
        if isinstance(key, str):
            vk = KEYS.get(key.lower())
            if vk is None:
                raise ValueError("unknown key name %r" % (key,))
            name = key.lower()
        else:
            vk = int(key)
            name = "vk:0x%02x" % vk
        self.ready()
        focus_before = self.focus()
        sent = self._press_raw(vk, modifiers)
        time.sleep(self.delay)
        focus_after = self.focus()
        self._log("key", {
            "transport": self.transport,
            "key": name,
            "modifiers": list(modifiers),
            "delivered": bool(sent),
            "focus_before": focus_before,
            "focus_after": focus_after,
            "note": note,
        })
        return focus_after

    def type_text(self, text, note=None):
        """Type characters one code point at a time (real WM_CHAR input path)."""
        focus_before = self.focus()
        delivered = 0
        for character in text:
            if self.transport == "sendinput":
                w32.send_key(0, unicode_char=ord(character))
                w32.send_key(0, up=True, unicode_char=ord(character))
            elif self.transport == "postmessage":
                target = self.focus() or self.hwnd
                w32.post_key(target, 0, char=ord(character))
            time.sleep(0.012)
            delivered += 1
        time.sleep(self.delay)
        self._log("text", {
            "transport": self.transport,
            "length": delivered,
            "focus_before": focus_before,
            "focus_after": self.focus(),
            "note": note,
        })
        return delivered

    def press_times(self, key, count, note=None):
        result = None
        for index in range(count):
            result = self.press(key, note=note if index == 0 else None)
        return result

    def alt_f4(self):
        return self.press("f4", ("alt",), note="request graceful close")
