# SPDX-License-Identifier: MIT
"""UI Automation access layer for the audit.

Every value is read through the raw IUIAutomationElement COM properties exposed
by the loaded Element, with the uiautomation wrapper properties as a documented
fallback. The audit records which source answered, so a wrapper shortcut can
never be mistaken for a raw provider value.
"""
from __future__ import annotations

PATTERN_IDS = {
    "InvokePattern": 10000,
    "SelectionPattern": 10001,
    "ValuePattern": 10002,
    "RangeValuePattern": 10003,
    "ScrollPattern": 10004,
    "ExpandCollapsePattern": 10005,
    "WindowPattern": 10009,
    "SelectionItemPattern": 10010,
    "TablePattern": 10012,
    "TextPattern": 10014,
    "TogglePattern": 10015,
    "TransformPattern": 10016,
    "LegacyIAccessiblePattern": 10018,
}

PROBE_ORDER = [
    "ValuePattern",
    "TextPattern",
    "SelectionPattern",
    "SelectionItemPattern",
    "TogglePattern",
    "InvokePattern",
    "RangeValuePattern",
    "ScrollPattern",
    "ExpandCollapsePattern",
    "WindowPattern",
    "TransformPattern",
    "LegacyIAccessiblePattern",
    "TablePattern",
]


def pattern_id(name):
    return PATTERN_IDS[name]


class Uia(object):
    def __init__(self):
        self.auto = None
        self.error = None
        self.version = None
        self.available = False
        try:
            import uiautomation as auto
        except Exception as exc:  # pragma: no cover - environment dependent
            self.error = "import uiautomation failed: %s" % (exc,)
            return
        self.auto = auto
        try:
            self.version = getattr(auto, "__version__", None) or getattr(
                getattr(auto, "version", None), "__version__", None)
        except Exception:
            self.version = None
        for target in (auto, getattr(auto, "uiautomation", None)):
            setter = getattr(target, "SetGlobalSearchTimeout", None)
            if callable(setter):
                try:
                    setter(5)
                    break
                except Exception:
                    continue
        self.available = True

    # -- element construction -------------------------------------------------
    def control(self, hwnd):
        if not self.available or not hwnd:
            return None
        try:
            return self.auto.ControlFromHandle(hwnd)
        except Exception:
            return None

    def _raw(self, control):
        try:
            return control.Element
        except Exception:
            return None

    def _read(self, control, com_name, wrapper_name, default=None):
        """Read a property from the raw element, then from the wrapper."""
        element = self._raw(control)
        if element is not None:
            try:
                value = getattr(element, com_name)
                if value is not None:
                    return value, "com"
            except Exception:
                pass
        try:
            value = getattr(control, wrapper_name)
            if value is not None:
                return value, "wrapper"
        except Exception:
            pass
        return default, "none"

    @staticmethod
    def _rect(value):
        if value is None:
            return None
        for attribute in ("left", "top", "right", "bottom"):
            if not hasattr(value, attribute):
                break
        else:
            try:
                return [int(value.left), int(value.top), int(value.right), int(value.bottom)]
            except Exception:
                return None
        try:
            items = list(value)
            if len(items) >= 4:
                return [int(items[0]), int(items[1]), int(items[2]), int(items[3])]
        except Exception:
            pass
        return None

    def type_name(self, type_id, fallback):
        table = getattr(self.auto, "ControlTypeNames", None) or {}
        try:
            name = table.get(int(type_id))
        except Exception:
            name = None
        return name or fallback or ("ControlType:%s" % (type_id,))

    def describe(self, control, patterns=False):
        if control is None:
            return None
        name, name_source = self._read(control, "CurrentName", "Name", "")
        type_id, _type_source = self._read(control, "CurrentControlType", "ControlType", 0)
        wrapper_type = ""
        try:
            wrapper_type = control.ControlTypeName
        except Exception:
            wrapper_type = ""
        record = {
            "name": name or "",
            "name_source": name_source,
            "control_type": self.type_name(type_id, wrapper_type),
            "control_type_id": int(type_id) if isinstance(type_id, int) else type_id,
            "class_name": self._read(control, "CurrentClassName", "ClassName", "")[0] or "",
            "automation_id": self._read(control, "CurrentAutomationId", "AutomationId", "")[0] or "",
            "localized_type": self._read(control, "CurrentLocalizedControlType",
                                         "LocalizedControlType", "")[0] or "",
            "enabled": bool(self._read(control, "CurrentIsEnabled", "IsEnabled", False)[0]),
            "keyboard_focusable": bool(self._read(control, "CurrentIsKeyboardFocusable",
                                                  "IsKeyboardFocusable", False)[0]),
            "has_focus": bool(self._read(control, "CurrentHasKeyboardFocus",
                                         "HasKeyboardFocus", False)[0]),
            "offscreen": bool(self._read(control, "CurrentIsOffscreen", "IsOffscreen", False)[0]),
            "help_text": self._read(control, "CurrentHelpText", "HelpText", "")[0] or "",
            "access_key": self._read(control, "CurrentAccessKey", "AccessKey", "")[0] or "",
            "accelerator_key": self._read(control, "CurrentAcceleratorKey",
                                          "AcceleratorKey", "")[0] or "",
            "framework": self._read(control, "CurrentFrameworkId", "FrameworkId", "")[0] or "",
            "process_id": self._read(control, "CurrentProcessId", "ProcessId", 0)[0] or 0,
            "native_hwnd": int(self._read(control, "CurrentNativeWindowHandle",
                                          "NativeWindowHandle", 0)[0] or 0),
            "rect": self._rect(self._read(control, "CurrentBoundingRectangle",
                                          "BoundingRectangle", None)[0]),
        }
        if patterns:
            record["patterns"] = self.patterns(control)
        return record

    def children(self, control):
        if control is None:
            return []
        try:
            return list(control.GetChildren() or [])
        except Exception:
            return []

    def patterns(self, control):
        """Probe which control patterns the element actually answers."""
        found = []
        element = self._raw(control)
        if element is not None:
            for name in PROBE_ORDER:
                try:
                    element.GetCurrentPattern(pattern_id(name))
                    found.append(name)
                except Exception:
                    continue
            return found
        for name in PROBE_ORDER:
            try:
                control.GetPattern(pattern_id(name))
                found.append(name)
            except Exception:
                continue
        return found

    def value(self, control):
        """Best-effort ValuePattern text; returns (text, error)."""
        element = self._raw(control)
        if element is not None:
            try:
                pattern = element.GetCurrentPattern(pattern_id("ValuePattern"))
            except Exception as exc:
                return (None, "ValuePattern unavailable: %s" % (exc,))
            for attribute in ("CurrentValue", "Value"):
                try:
                    return (getattr(pattern, attribute), None)
                except Exception:
                    continue
            return (None, "ValuePattern has no readable value")
        try:
            pattern = control.GetValuePattern()
            for attribute in ("Value", "CurrentValue"):
                try:
                    return (getattr(pattern, attribute), None)
                except Exception:
                    continue
        except Exception as exc:
            return (None, "GetValuePattern failed: %s" % (exc,))
        return (None, "no value attribute")

    def selection_names(self, control):
        """Names of the selected children, or (None, reason) when not exposed."""
        element = self._raw(control)
        if element is None:
            return (None, "no raw element")
        try:
            pattern = element.GetCurrentPattern(pattern_id("SelectionPattern"))
        except Exception as exc:
            return (None, "SelectionPattern unavailable: %s" % (exc,))
        try:
            selection = pattern.CurrentSelection
        except Exception as exc:
            return (None, "CurrentSelection unavailable: %s" % (exc,))
        names = []
        try:
            for index in range(selection.Length):
                item = selection.GetElement(index)
                try:
                    names.append(item.CurrentName)
                except Exception:
                    names.append("")
        except Exception as exc:
            return (None, "selection elements unavailable: %s" % (exc,))
        return (names, None)

    def focused(self):
        if not self.available:
            return None
        try:
            control = self.auto.GetFocusedControl()
        except Exception:
            return None
        if control is None:
            return None
        return self.describe(control, patterns=False)

    def dump(self, hwnd, max_depth=4, max_nodes=600, pattern_depth=1, max_children=60):
        """Nested dump of the element tree rooted at a window handle."""
        root = self.control(hwnd)
        budget = {"nodes": 0}
        return self._dump(root, 0, max_depth, max_nodes, pattern_depth, max_children, budget)

    def _dump(self, control, depth, max_depth, max_nodes, pattern_depth, max_children, budget):
        if control is None:
            return {"error": "no element for handle"}
        if budget["nodes"] >= max_nodes:
            return {"truncated": True}
        budget["nodes"] += 1
        node = self.describe(control, patterns=depth <= pattern_depth)
        node["depth"] = depth
        if depth >= max_depth:
            children = self.children(control)
            node["child_count"] = len(children)
            node["children_truncated"] = bool(children)
            return node
        children = self.children(control)
        node["child_count"] = len(children)
        node["children"] = [
            self._dump(child, depth + 1, max_depth, max_nodes, pattern_depth, max_children, budget)
            for child in children[:max_children]
        ]
        return node

    def find_by_hwnd(self, hwnd):
        control = self.control(hwnd)
        if control is None:
            return None
        return self.describe(control, patterns=True)
