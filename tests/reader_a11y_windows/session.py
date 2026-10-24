# SPDX-License-Identifier: MIT
"""Audit session: control identity, keyboard navigation, captures and dumps."""
from __future__ import annotations

import time
from pathlib import Path

import evidence
import png
import w32
from host import CONTROLS, IDS


class StepFailure(RuntimeError):
    pass


class Session(object):
    def __init__(self, host, keyboard, uia, trace, output):
        self.host = host
        self.kb = keyboard
        self.uia = uia
        self.trace = trace
        self.out = Path(output)
        self.shots = self.out / "screenshots"
        self.trees = self.out / "uia"
        self.crops = self.out / "focus-crops"
        for folder in (self.shots, self.trees, self.crops):
            folder.mkdir(parents=True, exist_ok=True)
        self.artifacts = {"screenshots": [], "uia_trees": [], "focus_crops": []}
        self.by_hwnd = {}
        self.last_capture = None
        self.transport_probe = {}
        self.focus_recoveries = 0

    # -- identity -------------------------------------------------------------
    def refresh_names(self):
        mapping = {}
        for name in CONTROLS:
            hwnd = self.host.control(name)
            if hwnd:
                mapping[hwnd] = name
        dialog = self.host.dialog_window()
        if dialog:
            for identifier, hwnd in self.host.dialog_controls(dialog).items():
                name = IDS.get(identifier)
                if name:
                    mapping[hwnd] = name
        self.by_hwnd = mapping
        return mapping

    def focus_hwnd(self):
        return self.kb.focus()

    def focus_name(self):
        hwnd = self.focus_hwnd()
        if not hwnd:
            return "none"
        self.refresh_names()
        if hwnd in self.by_hwnd:
            return self.by_hwnd[hwnd]
        return "%s:%s" % (w32.class_name(hwnd) or "?", w32.window_text(hwnd) or "")

    def locate(self, name):
        info = self.host.describe_control(name)
        dialog = self.host.dialog_window()
        if dialog:
            for identifier, hwnd in self.host.dialog_controls(dialog).items():
                if IDS.get(identifier) == name:
                    info = {
                        "id": identifier, "name": name, "present": True, "hwnd": hwnd,
                        "class": w32.class_name(hwnd), "text": w32.window_text(hwnd),
                        "enabled": bool(w32.user32.IsWindowEnabled(hwnd)),
                        "visible": bool(w32.user32.IsWindowVisible(hwnd)),
                        "tabstop": bool(w32.has_style(hwnd, w32.WS_TABSTOP)),
                        "rect": w32.window_rect(hwnd),
                    }
        return info

    def element(self, name):
        info = self.locate(name)
        if not info.get("present"):
            return {"control_id": CONTROLS.get(name), "missing": True}
        return {"control_id": info["id"], "class": info["class"], "hwnd": hex(info["hwnd"]),
                "window_text": info["text"], "tabstop": info["tabstop"],
                "rect": info["rect"]}

    def uia_at(self, hwnd, patterns=True):
        control = self.uia.control(hwnd)
        if control is None:
            return None
        return self.uia.describe(control, patterns=patterns)

    def uia_named(self, name, patterns=True):
        hwnd = self.locate(name).get("hwnd", 0)
        if not hwnd:
            return None
        return self.uia_at(hwnd, patterns=patterns)

    def list_item_names(self, name, limit=40):
        """Accessible names of the list items exposed by UI Automation."""
        control = self.uia.control(self.locate(name).get("hwnd", 0))
        names = []
        for child in self.uia.children(control)[:limit]:
            described = self.uia.describe(child)
            names.append(described.get("name") or "")
        return names

    # -- keyboard -------------------------------------------------------------
    def recover_focus(self, reason):
        """Restore a defined keyboard focus after the product loses it entirely.

        The loss is recorded by its own check; this call exists so the rest of
        the audit can still be measured on the same source.
        """
        before = self.focus_hwnd()
        after = w32.attach_and_focus(self.host.hwnd)
        self.focus_recoveries += 1
        self.trace.event("focus_recovery", {"reason": reason, "focus_before": before,
                                           "focus_after": after,
                                           "count": self.focus_recoveries})
        return after

    def ensure_focus(self, reason):
        """Keep the audit able to send keys: recover only when focus is lost."""
        if self.focus_hwnd():
            return True
        if self.recover_focus(reason):
            return True
        self.trace.event("focus_unrecoverable", {"reason": reason})
        return False

    def tab_step(self, backward=False, note=None):
        """One Tab press, retried once with a fresh foreground if focus is stuck."""
        modifiers = ("shift",) if backward else ()
        before = self.focus_name()
        if before == "none":
            self.ensure_focus("focus was lost before a Tab")
        self.kb.press("tab", modifiers, note=note)
        after = self.focus_name()
        if after == "none":
            self.ensure_focus("Tab did not restore focus")
            after = self.focus_name()
        if after == before and before != "none":
            self.kb.ready()
            self.kb.press("tab", modifiers, note="retry after re-activating the host")
            after = self.focus_name()
            self.trace.event("focus_retry", {"before": before, "after": after})
        return after

    def goto(self, target, limit=64, note=None):
        """Tab forward until the focused control is *target* (keyboard only)."""
        current = self.focus_name()
        if current == target:
            return True, []
        stops = []
        lost = 0
        for step in range(limit):
            name = self.tab_step(note=note if step == 0 else None)
            stops.append(name)
            if name == target:
                return True, stops
            if name == "none":
                lost += 1
                self.trace.event("focus_lost", {"step": step, "stops": stops[-6:]})
                if lost >= 3:
                    return False, stops
            else:
                lost = 0
        return False, stops

    def goto_back(self, target, limit=64, note=None):
        current = self.focus_name()
        if current == target:
            return True, []
        stops = []
        lost = 0
        for step in range(limit):
            name = self.tab_step(backward=True, note=note if step == 0 else None)
            stops.append(name)
            if name == target:
                return True, stops
            if name == "none":
                lost += 1
                if lost >= 3:
                    return False, stops
            else:
                lost = 0
        return False, stops

    def activate(self, target, limit=64):
        ok, stops = self.goto(target, limit=limit)
        if not ok:
            return False, stops
        self.kb.press("space", note="activate %s from the keyboard" % target)
        return True, stops

    def chain(self, limit=64, backward=False):
        """Walk Tab until a stop repeats; returns (ordered stops, repeated stop)."""
        order = []
        seen = set()
        for _ in range(limit):
            name = self.tab_step(backward=backward, note="tab order discovery")
            if name in seen:
                return order, name
            if name == "none":
                return order, "none"
            seen.add(name)
            order.append(name)
        return order, None

    # -- capture --------------------------------------------------------------
    def capture_now(self):
        capture = w32.capture_rgb(self.host.hwnd)
        if capture and "error" not in capture:
            self.last_capture = capture
            return capture
        self.trace.event("capture_failed", capture or {"error": "no result"})
        return None

    def shot(self, label):
        capture = self.capture_now()
        if not capture:
            self.trace.event("screenshot_missing", {"label": label})
            return None
        path = self.shots / (label + ".png")
        png.write_png(path, capture["width"], capture["height"], capture["rgb"])
        self.artifacts["screenshots"].append(str(path.relative_to(self.out)))
        self.trace.event("screenshot", {"label": label, "width": capture["width"],
                                        "height": capture["height"],
                                        "print_window": capture["print_window"]})
        return capture

    def dump(self, label, hwnd=None, depth=4):
        hwnd = hwnd or self.host.hwnd
        tree = self.uia.dump(hwnd, max_depth=depth)
        controls = {}
        self.host.refresh()
        for identifier, child in self.host._children.items():
            controls[str(identifier)] = hex(child)
        dialog = self.host.dialog_window()
        if dialog:
            for identifier, child in self.host.dialog_controls(dialog).items():
                controls[str(identifier)] = hex(child)
        payload = {
            "label": label,
            "hwnd": hwnd,
            "window_class": w32.class_name(hwnd),
            "window_text": w32.window_text(hwnd),
            "taken_at_ms": int((time.time() - self.trace.started) * 1000),
            "uia_available": self.uia.available,
            "control_ids": controls,
            "tree": tree,
        }
        path = self.trees / (label + ".json")
        evidence.write_json(path, payload)
        self.artifacts["uia_trees"].append(str(path.relative_to(self.out)))
        self.trace.event("uia_tree", {"label": label, "hwnd": hwnd,
                                      "path": str(path.relative_to(self.out))})
        return payload

    def control_rect_in_window(self, name):
        info = self.locate(name)
        rect = info.get("rect")
        origin = w32.window_rect(self.host.hwnd)
        if not rect or not origin:
            return None
        return [rect[0] - origin[0], rect[1] - origin[1], rect[2] - origin[0], rect[3] - origin[1]]

    def focus_visibility(self, target, alternate, label, samples=3):
        """Measure whether *target* repaints when it gains and loses focus."""
        result = {"target": target, "alternate": alternate, "samples": []}
        ok, stops = self.goto(target)
        result["focused_target"] = ok
        result["stops_to_target"] = stops
        if not ok:
            result["reason"] = "keyboard could not reach %s" % target
            return result
        rect = self.control_rect_in_window(target)
        result["rect_in_window"] = rect
        if not rect:
            result["reason"] = "no rectangle for %s" % target
            return result
        best = None
        for attempt in range(samples):
            time.sleep(0.18 + 0.12 * attempt)
            focused = self.capture_now()
            ok_alt, _alt_stops = self.goto(alternate)
            time.sleep(0.12)
            unfocused = self.capture_now()
            if not focused or not unfocused:
                continue
            width_a, height_a, crop_a = png.crop(focused["rgb"], focused["width"],
                                                 focused["height"], rect)
            width_b, height_b, crop_b = png.crop(unfocused["rgb"], unfocused["width"],
                                                 unfocused["height"], rect)
            if not crop_a or not crop_b or (width_a, height_a) != (width_b, height_b):
                continue
            changed = png.changed_bytes(crop_a, crop_b)
            sample = {"attempt": attempt, "width": width_a, "height": height_a,
                      "changed_bytes": changed,
                      "changed_pixels_estimate": changed // 3}
            result["samples"].append(sample)
            if best is None or changed > best["changed_bytes"]:
                best = sample
                suffix = "-%s-%s" % (target, attempt)
                png.write_png(self.crops / ("before" + suffix + ".png"), width_a, height_a, crop_a)
                png.write_png(self.crops / ("after" + suffix + ".png"), width_b, height_b, crop_b)
                self.artifacts["focus_crops"].append(
                    str((self.crops / ("before" + suffix + ".png")).relative_to(self.out)))
                self.artifacts["focus_crops"].append(
                    str((self.crops / ("after" + suffix + ".png")).relative_to(self.out)))
            if not self.goto(target):
                break
        if best:
            result["changed_bytes"] = best["changed_bytes"]
            result["changed_pixels_estimate"] = best["changed_pixels_estimate"]
            result["visible_focus"] = best["changed_bytes"] > 0
        else:
            result["visible_focus"] = None
            result["reason"] = result.get("reason") or "no comparable capture pair"
        self.trace.event("focus_visibility", {"label": label, "target": target,
                                              "changed_bytes": result.get("changed_bytes"),
                                              "visible_focus": result.get("visible_focus")})
        return result

    # -- state ----------------------------------------------------------------
    def status(self):
        return self.host.status()

    def page_label(self):
        return self.host.page_label()

    def wait_status_contains(self, needle, timeout=60):
        return self.host.wait_for(lambda: needle in self.host.status(), timeout=timeout,
                                  interval=0.2, label="status contains %r" % needle)

    def require(self, condition, message):
        if not condition:
            raise StepFailure(message)
