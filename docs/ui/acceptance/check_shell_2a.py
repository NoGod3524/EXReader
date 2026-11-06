# SPDX-License-Identifier: MIT
"""2a step 2 acceptance: flat reading screen and top bar.

Runs shell-2a.txt in a reader built with EXR_READER_WINDOWS_SHELL=ON and
judges four of the five step-2 checks; the fifth (client-area pixel regression
of the legacy panel) is compare_shots.py over phase-a/b/c screenshots.

  topbar   56 high: rows 0..54 layer.page #FFFFFF, row 55 hairline #F0F0F0,
           page below with no 3D edge; nothing else drawn in the bar outside
           the title and the two circles; only 3 visible children
  spec     radii, spacing and colours of UI-SPEC sections 1, 5, 7 and
           WIREFRAMES section 2: title starts at x=24 and stops 16 before 目录;
           circles 40 across (radius 20), 8 from the top, 8 apart, 16 from the
           right edge; normal / hover / pressed / focus / disabled colours;
           title faces not synthesised
  uia      UI Automation, client area only: exactly 3 operable elements, none unnamed
  legacy   after Alt+Left all 17 control IDs (101..117) are reachable (in-app
           check and UI Automation)

usage: check_shell_2a.py EXE SAMPLE_DIR OUT_DIR
EXE must sit next to libexreader.dll; SAMPLE_DIR holds Sample.epub.
UI Automation is read with uiautomation==2.0.29, the package and pin of the
Windows accessibility audit. Exit code 0 only when every drive step passed and
all four checks pass.
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
# UI-SPEC tokens (light theme).
PAGE, HAIRLINE, TEXT, DISABLED, ACCENT = 0xFFFFFF, 0xF0F0F0, 0x1D1D1F, 0xAEAEB2, 0x1A73E8
HOVER, PRESSED = 0xF1F7FE, 0xE4EEFC
TOPBAR, TARGET, SPACE_1, SPACE_2, SPACE_3 = 56, 40, 8, 16, 24
LEGACY_IDS = [str(i) for i in range(101, 118)]


def rgb(value):
    return ((value >> 16) & 255, (value >> 8) & 255, value & 255)


def hexc(pixel):
    return '#%02X%02X%02X' % pixel[:3]


def main_window(pid):
    user32 = ctypes.windll.user32
    found = []
    proc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def visit(hwnd, _):
        owner = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        name = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, name, 64)
        if owner.value == pid and name.value == "EXReaderHost":
            found.append(hwnd)
        return True

    user32.EnumWindows(proc(visit), 0)
    return found[0] if found else None


def details(text):
    out = {}
    for part in text.split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            out[key] = value
    return out


def uia(hwnd, path):
    """Client-area UI Automation tree through the native COM client."""
    import uiautomation as auto
    patterns = (10000, 10015, 10002, 10010, 10005)  # Invoke Toggle Value SelectionItem ExpandCollapse
    rows = []

    def walk(control, depth):
        for child in control.GetChildren():
            kind = child.ControlTypeName
            if kind in ("TitleBarControl", "MenuBarControl"):
                continue  # the window frame, not the reader's UI
            operable = bool(child.IsKeyboardFocusable) or any(child.GetPattern(p) for p in patterns)
            rows.append({"depth": depth, "type": kind, "name": child.Name, "automation_id": child.AutomationId,
                         "focusable": bool(child.IsKeyboardFocusable), "enabled": bool(child.IsEnabled),
                         "offscreen": bool(child.IsOffscreen), "operable": operable})
            if depth < 6:
                walk(child, depth + 1)

    walk(auto.ControlFromHandle(hwnd), 0)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return rows


class Shot:
    """A screenshot addressed in client coordinates."""

    def __init__(self, path, origin, client):
        self.image = Image.open(path).convert("RGB")
        self.ox, self.oy = (int(v) for v in origin.split(","))
        self.w, self.h = (int(v) for v in client.split("x"))

    def px(self, x, y):
        return self.image.getpixel((self.ox + x, self.oy + y))

    def circle(self, cx, cy, fill):
        """Extent of the filled circle along its centre row and column:
        pixels at least half way from the page colour to the fill colour."""
        page, target = rgb(PAGE), rgb(fill)
        span = max(abs(a - b) for a, b in zip(page, target)) or 1

        def covered(x, y):
            p = self.px(x, y)
            return max(abs(a - b) for a, b in zip(p, page)) * 2 >= span

        xs = [x for x in range(cx - 24, cx + 24) if covered(x, cy)]
        ys = [y for y in range(max(0, cy - 24), cy + 24) if covered(cx, y)]
        return (min(xs), max(xs) + 1, min(ys), max(ys) + 1) if xs and ys else None


def judge_spec(shots, check):
    s = shots["31"]
    w = s.w
    toc_c, set_c = (w - 84, 28), (w - 36, 28)
    out, ok = {}, True

    def record(name, value, passed):
        nonlocal ok
        out[name] = {"value": value, "pass": bool(passed)}
        ok &= bool(passed)

    # Title: first ink at x 24 (+ side bearing), last ink before 目录 − 16.
    ink = [x for y in range(14, 42) for x in range(0, w - 104 - 16) if s.px(x, y) != rgb(PAGE)]
    record("title_left_px", min(ink) if ink else None, ink and SPACE_3 <= min(ink) <= SPACE_3 + 2)
    record("title_right_limit", {"last_ink": max(ink) if ink else None, "limit": w - 104 - SPACE_2},
           ink and max(ink) < w - 104 - SPACE_2)
    # Normal state: both circles are page colour away from the glyph, icon present.
    for name, (cx, cy) in (("toc", toc_c), ("settings", set_c)):
        record(f"normal_{name}_bg", hexc(s.px(cx - 15, cy)), s.px(cx - 15, cy) == rgb(PAGE))
        dark = min((s.px(x, y) for x in range(cx - 10, cx + 10) for y in range(cy - 10, cy + 10)), key=sum)
        record(f"normal_{name}_icon_darkest", hexc(dark), dark == rgb(TEXT))
    # No accent anywhere in the bar while focus cues are hidden.
    accent_bar = sum(1 for y in range(TOPBAR) for x in range(w) if s.px(x, y) == rgb(ACCENT))
    record("normal_no_focus_outline", accent_bar, accent_bar == 0)
    # Hover (目录) and pressed (设置): fill colour and circle geometry.
    for key, name, (cx, cy), colour in (("32", "hover_toc", toc_c, HOVER), ("33", "pressed_settings", set_c, PRESSED)):
        shot = shots[key]
        record(f"{name}_fill", hexc(shot.px(cx - 15, cy)), shot.px(cx - 15, cy) == rgb(colour))
        box = shot.circle(cx, cy, colour)
        record(f"{name}_circle", box, box and box[1] - box[0] == TARGET and box[3] - box[2] == TARGET)
        if box and name == "hover_toc":
            record("toc_circle_left_right_top", [box[0], box[1], box[2]],
                   box[0] == w - SPACE_2 - TARGET - SPACE_1 - TARGET and box[2] == SPACE_1)
            record("radius_round", (box[1] - box[0]) / 2, (box[1] - box[0]) / 2 == TARGET / 2)
        if box and name == "pressed_settings":
            record("settings_right_gap", w - box[1], w - box[1] == SPACE_2)
            record("settings_top", box[2], box[2] == SPACE_1)
    if out.get("toc_circle_left_right_top", {}).get("value") and out.get("settings_right_gap", {}).get("value") is not None:
        gap = (w - SPACE_2 - TARGET) - out["toc_circle_left_right_top"]["value"][1]
        record("circle_gap", gap, gap == SPACE_1)
    # Focus (目录): 2 px accent outside the 40 circle, no fill inside.
    f = shots["34"]
    cx, cy = toc_c
    # The outline spans radius 20..22 around the circle centre (a pixel corner).
    # Pixels lying wholly inside that band must be exactly the accent; the
    # band's two edge pixels are anti-aliased and only reported.
    ring = [hexc(f.px(cx - 21, cy)), hexc(f.px(cx + 20, cy)), hexc(f.px(cx, cy - 21)), hexc(f.px(cx, cy + 20))]
    record("focus_toc_outline", ring, all(c == hexc(rgb(ACCENT)) for c in ring))
    edge = [hexc(f.px(cx - 22, cy)), hexc(f.px(cx - 20, cy))]
    record("focus_toc_outline_edges_antialiased", edge, True)
    record("focus_toc_inside", hexc(f.px(cx - 15, cy)), f.px(cx - 15, cy) == rgb(PAGE))
    record("focus_toc_outline_clear_of_circle", [hexc(f.px(cx - 23, cy)), hexc(f.px(cx - 19, cy))],
           f.px(cx - 23, cy) == rgb(PAGE) and f.px(cx - 19, cy) == rgb(PAGE))
    # Disabled (设置): no fill, icon in text.disabled.
    d = shots["35"]
    cx, cy = set_c
    dark = min((d.px(x, y) for x in range(cx - 10, cx + 10) for y in range(cy - 10, cy + 10)), key=sum)
    record("disabled_settings_bg", hexc(d.px(cx - 15, cy)), d.px(cx - 15, cy) == rgb(PAGE))
    record("disabled_settings_icon_darkest", hexc(dark), dark == rgb(DISABLED))
    # Faces: the title's 600 weight is a real face for Latin and CJK.
    record("title_faces", {k: check.get(k) for k in ("title_family", "latin_simulations", "cjk_simulations")},
           check.get("latin_simulations") == "0" and check.get("cjk_simulations") == "0")
    return out, ok


def judge_topbar(shot, check):
    w, h = shot.w, shot.h
    bad = []
    toc_box = (w - 104 - 2, w - 64 + 2)
    set_box = (w - 56 - 2, w - 16 + 2)
    for y in range(TOPBAR):
        for x in range(w):
            if SPACE_3 <= x < w - 104 - SPACE_2 and 14 <= y < 42:
                continue  # title
            if (toc_box[0] <= x < toc_box[1] or set_box[0] <= x < set_box[1]) and 6 <= y < 50:
                continue  # buttons
            want = rgb(HAIRLINE) if y == TOPBAR - 1 else rgb(PAGE)
            if shot.px(x, y) != want:
                bad.append((x, y, hexc(shot.px(x, y))))
    edges = [shot.px(x, y) for y in range(TOPBAR, h) for x in (0, 1, w - 2, w - 1)]
    edge_bad = sum(1 for p in edges if p != rgb(PAGE))
    rows = [hexc(shot.px(8, y)) for y in (0, 54, 55, 56)]
    return {"column_x8_rows_0_54_55_56": rows, "stray_pixels_in_bar": len(bad), "first_stray": bad[:3],
            "page_edge_non_page_pixels": edge_bad, "visible_children": check.get("visible_children"),
            "page_top": check.get("page_top"), "page_edge_style": check.get("page_edge"),
            "pass": rows == ["#FFFFFF", "#FFFFFF", "#F0F0F0", "#FFFFFF"] and not bad and edge_bad == 0
            and check.get("visible_children") == "3" and check.get("page_top") == str(TOPBAR)
            and check.get("page_edge") == "0"}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    exe, sample, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve()
    shutil.rmtree(out, ignore_errors=True)
    evidence, data = out / "evidence", out / "data"
    evidence.mkdir(parents=True)
    data.mkdir()
    script = out / "shell-2a.script"
    script.write_text((HERE / "shell-2a.txt").read_text(encoding="utf-8").replace("@@SAMPLE@@", str(sample)),
                      encoding="utf-8", newline="\n")
    env = dict(os.environ, EXREADER_HOST_ACCEPTANCE="1")
    process = subprocess.Popen([str(exe), "--drive", str(script), "--evidence", str(evidence), "--data", str(data),
                                "--library", str(data / "library.sqlite"), "--phase", "1"], env=env)
    log = evidence / "drive.log"
    trees, deadline = {}, time.time() + 180
    while process.poll() is None and time.time() < deadline:
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines() if log.exists() else []
        shots = sum(1 for line in lines if line.startswith("STEP\t") and line.split("\t")[2] == "snapshot")
        for count, name in ((6, "shell"), (7, "legacy")):
            if shots == count and name not in trees:
                pid = int(next(l for l in lines if l.startswith("HOST\t")).split("pid=")[1].split("\t")[0])
                trees[name] = uia(main_window(pid), out / f"uia-{name}.json")
        time.sleep(0.2)
    if process.poll() is None:
        process.kill()
    exit_code = process.wait()
    steps = [line.split("\t") for line in log.read_text(encoding="utf-8").splitlines() if line.startswith("STEP\t")]
    failed = [f"{s[1]} {s[2]} {s[4]}" for s in steps if s[3] != "PASS"]
    checks = [details(s[4]) for s in steps if s[2] == "check"]
    shell_check = next((c for c in checks if c.get("active") == "1"), {})
    fonts = next((c for c in checks if "latin_simulations" in c), {})
    reach = [c for c in checks if "reachable" in c]

    notes = [line for line in log.read_text(encoding="utf-8").splitlines() if line.startswith("NOTE	")]
    activations = [n for n in notes if "activating window for focus checks" in n]
    for n in activations:
        print("activating window for focus checks (drive step %s)" % n.split("	")[1])
    result = {"exit": exit_code, "steps": len(steps), "failed_steps": failed, "focus_activations": len(activations)}
    shots = {}
    if shell_check.get("client_origin"):
        for key, name in (("31", "31-shell"), ("32", "32-hover-toc"), ("33", "33-pressed-settings"),
                          ("34", "34-focus-toc"), ("35", "35-disabled-settings")):
            shots[key] = Shot(evidence / f"{name}.png", shell_check["client_origin"], shell_check["client"])
    result["topbar"] = judge_topbar(shots["31"], shell_check) if shots else {"pass": False}
    spec, spec_ok = judge_spec(shots, fonts) if shots else ({}, False)
    result["spec"] = {"items": spec, "pass": spec_ok}

    rows = trees.get("shell", [])
    operable = [r for r in rows if r["operable"] and not r["offscreen"]]
    result["uia"] = {"elements": len(rows), "operable": [[r["type"], r["name"], r["automation_id"]] for r in operable],
                     "unnamed": sum(1 for r in operable if not r["name"]),
                     "pass": bool(rows) and len(operable) == 3 and all(r["name"] for r in operable)}

    rows = trees.get("legacy", [])
    present = {r["automation_id"] for r in rows if r["operable"] and not r["offscreen"]}
    missing = [i for i in LEGACY_IDS if i not in present]
    result["legacy"] = {"in_app": [r.get("reachable") for r in reach], "uia_missing": missing,
                        "pass": bool(rows) and not missing and len(reach) == 2
                        and all(r.get("reachable") == "17" for r in reach)}
    ok = exit_code == 0 and not failed and all(result[k]["pass"] for k in ("topbar", "spec", "uia", "legacy"))
    result["pass"] = ok
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
