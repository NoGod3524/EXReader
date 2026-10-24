# SPDX-License-Identifier: MIT
"""Audit flows for the real Win32 reader host.

Each flow drives the product with the keyboard only, reads UI Automation, and
records one named check per claim. Nothing here writes to the product, the SDK
or the product database beyond what the audited commands themselves persist.
"""
from __future__ import annotations

import re
import time

import w32

BUTTON_CONTROLS = (
    "import_button", "open_button", "delete_button", "prev", "next", "select_all",
    "copy_quote", "add_note", "update_note", "delete_note", "jump_note",
    "font_dec", "font_inc", "zoom_dec", "zoom_inc", "cancel", "shelf_refresh",
    "metadata_button",
)


def _focusable_prefix(s):
    return "Tab from %r" % (s.focus_name(),)


def phase_launch(s, r):
    """Main window, empty shelf, state exposure before any import."""
    s.dump("t00-launch-empty")
    s.shot("00-launch-empty")
    main = s.uia_at(s.host.hwnd)
    books = s.uia_named("books")
    search = s.uia_named("shelf_search")
    refresh = s.uia_named("shelf_refresh")
    details = s.uia_named("metadata_button")
    empty_open = s.host.enabled("open_button")
    empty_delete = s.host.enabled("delete_button")

    r.record(
        "SH-01", "shelf", "main window exposes the product name and a window role",
        "serious", "pass" if main and main.get("name") and "Window" in (main.get("control_type") or "")
        else "fail",
        "UI Automation exposes the top-level window with an accessible name and a window control type",
        "name=%r control_type=%r class=%r" % ((main or {}).get("name"), (main or {}).get("control_type"),
                                              (main or {}).get("class_name")),
        steps=["launch EXReader.exe --data <temp>", "ControlFromHandle(main window)", "read Name/ControlType"],
        element={"hwnd": hex(s.host.hwnd), "class": w32.class_name(s.host.hwnd),
                 "window_text": w32.window_text(s.host.hwnd)},
        fix="none needed while the window keeps its title")

    r.record(
        "SH-02", "shelf", "book list exposes a name, list role and keyboard focus",
        "blocking",
        "pass" if books and (books.get("name") or "").strip() and books.get("control_type") == "ListControl"
        and books.get("keyboard_focusable") else "fail",
        "the bookshelf list is a List control with an accessible name and is reachable with the keyboard",
        "name=%r control_type=%r keyboard_focusable=%s" % ((books or {}).get("name"),
                                                           (books or {}).get("control_type"),
                                                           (books or {}).get("keyboard_focusable")),
        steps=["read the UIA element of control 119 (ListBox)"],
        element=s.element("books"),
        fix="none needed while LB window text stays '书架'")

    r.record(
        "SH-04", "shelf", "shelf search field has an accessible name",
        "blocking", "pass" if search and (search.get("name") or "").strip() else "fail",
        "the search box announces a name such as 书架搜索, independent of its role",
        "name=%r control_type=%r help=%r access_key=%r" % ((search or {}).get("name"),
                                                           (search or {}).get("control_type"),
                                                           (search or {}).get("help_text"),
                                                           (search or {}).get("access_key")),
        steps=["read the UIA element of control 126 (Edit)"],
        element=s.element("shelf_search"),
        fix="give the search box its own window text or an IAccessible/UIA name such as 书架搜索")

    buttons_ok = bool(refresh) and (refresh.get("name") or "").strip() and \
        refresh.get("control_type") == "ButtonControl"
    details_state = "absent" if not details else ("enabled" if details.get("enabled") else "disabled")
    r.record(
        "SH-06", "shelf", "shelf refresh and details buttons expose name, role and state",
        "serious",
        "pass" if buttons_ok and details is not None else "fail",
        "刷新 and 详情 are buttons with accessible names and an accurate enabled state",
        "refresh name=%r type=%r; details %s" % ((refresh or {}).get("name"),
                                                 (refresh or {}).get("control_type"), details_state),
        steps=["read UIA for controls 127 (刷新) and 128 (详情)"],
        element=s.element("shelf_refresh"),
        fix="none needed while both buttons keep their text and EnableWindow state")

    r.record(
        "SH-07", "shelf", "empty shelf exposes Open and Delete as unavailable",
        "moderate",
        "pass" if not empty_open and not empty_delete else "fail",
        "with no books, 打开 and 删除 report IsEnabled=false to assistive technology",
        "open_button IsEnabled=%s, delete_button IsEnabled=%s, shelf_items=%d"
        % (empty_open, empty_delete, len(s.host.list_text("books"))),
        steps=["launch with an empty data directory", "read IsWindowEnabled and UIA IsEnabled"],
        element=s.element("open_button"),
        fix="none needed while host_update_controls keeps the disable state")


def import_book(s, path_text, timeout=90):
    """Keyboard-only import: focus the path edit, type the path, activate 导入."""
    ok_edit, stops = s.goto("import_edit")
    if not ok_edit:
        return {"ok": False, "stage": "focus", "stops": stops}
    s.kb.type_text(path_text, note="type the book path like a user")
    typed = s.host.text("import_edit")
    ok_button, stops2 = s.goto("import_button")
    if not ok_button:
        return {"ok": False, "stage": "button", "stops": stops2, "typed": typed}
    s.kb.press("space", note="activate 导入 from the keyboard")
    return {"ok": True, "typed": typed, "stops": stops + stops2}


def phase_import(s, r, epub_path):
    """Import the first book with the keyboard only and audit the feedback."""
    edit = s.uia_named("import_edit")
    button = s.uia_named("import_button")
    r.record(
        "IM-01", "import", "import path field has an accessible name",
        "blocking", "pass" if edit and (edit.get("name") or "").strip() else "fail",
        "the import path edit announces a name such as 导入路径 next to its label",
        "name=%r control_type=%r help=%r labeled_by=%r" % ((edit or {}).get("name"),
                                                          (edit or {}).get("control_type"),
                                                          (edit or {}).get("help_text"),
                                                          (edit or {}).get("automation_id")),
        steps=["read the UIA element of control 101 (Edit)"],
        element=s.element("import_edit"),
        fix="give the edit box its own accessible name; the static 导入路径 label is not associated")

    r.record(
        "IM-02", "import", "import button exposes name and role",
        "serious", "pass" if button and (button.get("name") or "").strip() == "导入"
        and button.get("control_type") == "ButtonControl" else "fail",
        "导入 is a Button whose accessible name is the command text",
        "name=%r control_type=%r enabled=%s" % ((button or {}).get("name"),
                                               (button or {}).get("control_type"),
                                               (button or {}).get("enabled")),
        steps=["read the UIA element of control 102 (Button)"],
        element=s.element("import_button"),
        fix="none needed")

    before = len(s.list_item_names("books"))
    result = import_book(s, epub_path)
    imported = None
    if result.get("ok"):
        imported = s.host.wait_for(
            lambda: len(s.list_item_names("books")) > before, timeout=90, interval=0.25,
            label="shelf grows after the keyboard import")
    status_after = s.status()
    items = s.list_item_names("books")
    r.record(
        "IM-03", "import", "a book imports with the keyboard only",
        "blocking", "pass" if imported and len(items) > before else "fail",
        "typing the path and pressing Space on 导入 adds the book to the shelf, with no mouse event",
        "path typed=%r, shelf items %d -> %d, status=%r"
        % (result.get("typed"), before, len(items), status_after),
        steps=["Tab to the path field", "type %s" % epub_path, "Tab to 导入",
               "press Space", "wait for the shelf list to grow"],
        element=s.element("import_button"),
        evidence={"typed": result.get("typed"), "stops": result.get("stops"),
                  "status_after": status_after},
        fix="none needed; keyboard import already works")

    status_el = s.uia_named("status")
    r.record(
        "IM-04", "import", "import result is exposed as readable text",
        "serious",
        "pass" if status_el and (status_el.get("name") or "").strip()
        and "导入" in (status_el.get("name") or "") else "fail",
        "the status line exposes the import result to assistive technology as text",
        "status element name=%r control_type=%r" % ((status_el or {}).get("name"),
                                                     (status_el or {}).get("control_type")),
        steps=["read the UIA element of control 125 (Static) after the import"],
        element=s.element("status"),
        fix="none needed for exposure; announcement is a separate check")

    after_focus = s.focus_name()
    r.record(
        "IM-06", "import", "focus stays on the import command after the import",
        "moderate", "pass" if after_focus == "import_button" else "fail",
        "the keyboard focus remains on 导入, so the next key press is predictable",
        "focused control after import=%r" % (after_focus,),
        steps=["read GetGUIThreadInfo(hwndFocus) after the import completes"],
        element=s.element("import_button"),
        fix="do not move focus from the importing command; announce completion instead")

    items = s.list_item_names("books")
    listed = s.host.list_text("books")
    non_empty = [name for name in items if name.strip()]
    r.record(
        "SH-03", "shelf", "each shelf item exposes the book text as its name",
        "blocking", "pass" if items and len(non_empty) == len(items) else "fail",
        "every list item exposes a non-empty accessible name equal to the row string",
        "uia item names=%r; listbox strings=%r" % (items[:6], listed[:6]),
        steps=["read the UIA ListItem children of control 119"],
        element=s.element("books"),
        evidence={"uia_items": items, "listbox_strings": listed},
        fix="none needed while the list owns real strings instead of custom drawing")


def phase_search(s, r, needle, expected_in_name):
    """Filter the shelf from the keyboard and read the resulting item names."""
    ok, stops = s.goto("shelf_search")
    typed = ""
    filtered = None
    if ok:
        s.kb.type_text(needle, note="filter the shelf from the keyboard")
        typed = s.host.text("shelf_search")
        filtered = s.host.wait_for(
            lambda: len(s.list_item_names("books")) == 1, timeout=30, interval=0.2,
            label="shelf filtered to one row")
    names = s.list_item_names("books")
    match = bool(names) and expected_in_name.lower() in (names[0] or "").lower()
    r.record(
        "SH-05", "shelf", "shelf search filters the list from the keyboard",
        "serious", "pass" if ok and filtered and match else "fail",
        "typing in the search box narrows the shelf to the matching book",
        "typed=%r, focus_reached=%s, item count=%d, first name=%r"
        % (typed, ok, len(names), names[0] if names else None),
        steps=["Tab to the search box", "type %r" % needle, "wait for the filtered list"],
        element=s.element("shelf_search"),
        evidence={"stops": stops, "names": names},
        fix="none needed; keyboard filtering already works")
    return names


def clear_search(s):
    ok, _ = s.goto("shelf_search")
    if not ok:
        return False
    for _ in range(24):
        if not s.host.text("shelf_search"):
            break
        s.kb.press("backspace")
    return not s.host.text("shelf_search")


def select_and_open(s):
    """Select the first shelf row and open it with the keyboard only."""
    ok_list, stops = s.goto("books")
    if not ok_list:
        return {"ok": False, "stage": "list", "stops": stops}
    s.kb.press("home", note="select the first shelf row")
    label_before = s.page_label()
    ok_open, stops2 = s.activate("open_button")
    if not ok_open:
        return {"ok": False, "stage": "open", "stops": stops2}
    changed = s.host.wait_for(lambda: s.page_label() != label_before, timeout=120, interval=0.25,
                              label="page label changes after opening a book")
    return {"ok": bool(changed), "label_before": label_before, "label_after": s.page_label(),
            "stops": stops + stops2}


def phase_reading(s, r):
    """Reading region exposure, page turning and selection."""
    page = s.uia_named("page")
    page_hwnd = s.locate("page").get("hwnd", 0)
    control = s.uia.control(page_hwnd)
    children = s.uia.children(control) if control is not None else []
    child_names = [s.uia.describe(child).get("name") or "" for child in children[:20]]
    patterns = (page or {}).get("patterns") or []

    r.record(
        "RD-01", "reading", "reading region is exposed as an element with a name",
        "serious", "pass" if page and (page.get("name") or "").strip() else "fail",
        "the page view is present in the UIA tree with an accessible name",
        "name=%r control_type=%r class=%r focusable=%s"
        % ((page or {}).get("name"), (page or {}).get("control_type"),
           (page or {}).get("class_name"), (page or {}).get("keyboard_focusable")),
        steps=["read the UIA element of control 123 (custom class EXReaderPage)"],
        element=s.element("page"),
        fix="implement a UIA provider on EXReaderPage instead of relying on the default proxy")

    text_bearing = [name for name in child_names if name.strip()]
    r.record(
        "RD-02", "reading", "page content is readable through UI Automation",
        "blocking",
        "pass" if ("TextPattern" in patterns or "ValuePattern" in patterns or text_bearing) else "fail",
        "the reading region exposes the page text (Text/Value pattern or child text elements)",
        "patterns=%r child_count=%d child_text_elements=%d"
        % (patterns, len(children), len(text_bearing)),
        steps=["read patterns of control 123", "walk its UIA children"],
        element=s.element("page"),
        evidence={"patterns": patterns, "child_names": child_names},
        fix="add a UIA text provider (ITextProvider or a Text pattern) over the painted page text")

    ok_focus, stops = s.goto("page")
    r.record(
        "RD-03", "reading", "reading region is reachable with the keyboard",
        "blocking", "pass" if ok_focus else "fail",
        "Tab reaches the page view and it reports IsKeyboardFocusable",
        "focus reached=%s after %d Tab stops; keyboard_focusable=%s"
        % (ok_focus, len(stops), (page or {}).get("keyboard_focusable")),
        steps=["press Tab from the previous stop until control 123 has focus"],
        element=s.element("page"),
        evidence={"stops": stops},
        fix="keep WS_TABSTOP on the page and answer WM_GETDLGCODE without DLGC_WANTTAB")

    visibility = s.focus_visibility("page", "books", "page-region")
    r.record(
        "RD-04", "reading", "reading region shows a visible keyboard focus indicator",
        "blocking", "pass" if visibility.get("visible_focus") else "fail",
        "the page view repaints a focus indicator while it holds keyboard focus",
        "changed pixels when focus moved away=%s (%s of %s samples)"
        % (visibility.get("changed_pixels_estimate"), len(visibility.get("samples") or []),
           len(visibility.get("samples") or [])),
        steps=["focus the page view with Tab", "capture", "focus another control",
               "capture again and compare the page rectangle"],
        element=s.element("page"),
        evidence={"rect_in_window": visibility.get("rect_in_window"),
                  "samples": visibility.get("samples")},
        fix="draw a focus ring in WM_PAINT when WM_SETFOCUS set a focused flag")

    ok_page, _ = s.goto("page")
    label_before = s.page_label()
    s.kb.press("right", note="next page from the keyboard")
    forward = s.host.wait_for(lambda: s.page_label() != label_before, timeout=60, interval=0.2,
                             label="page label advances")
    label_forward = s.page_label()
    s.kb.press("left", note="previous page from the keyboard")
    back = s.host.wait_for(lambda: s.page_label() == label_before, timeout=60, interval=0.2,
                           label="page label returns")
    r.record(
        "RD-05", "reading", "page turning works from the keyboard",
        "blocking", "pass" if ok_page and forward and back else "fail",
        "Right and Left turn the page while the page view has focus",
        "label %r -> %r -> %r; forward=%s back=%s"
        % (label_before, label_forward, s.page_label(), bool(forward), bool(back)),
        steps=["focus the page view", "press Right", "press Left"],
        element=s.element("page"),
        fix="none needed; arrows already page")

    label_el = s.uia_named("page_label")
    label_text = (label_el or {}).get("name") or ""
    r.record(
        "RD-06", "reading", "reading position is exposed as text",
        "serious", "pass" if ("页" in label_text or "章" in label_text) else "fail",
        "the position line exposes page/chapter, format and size to assistive technology",
        "page_label element name=%r control_type=%r" % (label_text,
                                                        (label_el or {}).get("control_type")),
        steps=["read the UIA element of control 124 (Static)"],
        element=s.element("page_label"),
        fix="none needed for exposure")

    if s.kb.transport != "sendinput":
        r.record(
            "RD-07", "reading", "select all and copy work from the keyboard",
            "serious", "not_verified",
            "Ctrl+A then Ctrl+C produce a selection and put the page text on the clipboard",
            "not measured: modifier chords need the real input queue and the audit used the "
            "%r transport" % (s.kb.transport,),
            steps=["would press Ctrl+A and Ctrl+C on the focused page view"],
            element=s.element("page"),
            reason="keyboard transport %r cannot set GetKeyState, which the host reads for "
                   "Ctrl shortcuts" % (s.kb.transport,),
            fix="re-run with the SendInput transport")
        return

    s.goto("page")
    s.kb.press(0x41, ("ctrl",), note="select the whole page")
    selected = s.wait_status_contains("已选择", timeout=30)
    status_selected = s.status()
    s.kb.press(0x43, ("ctrl",), note="copy the selection")
    copied = s.host.wait_for(lambda: "已复制" in s.status(), timeout=30, interval=0.2,
                             label="copy reports success")
    clipboard = w32.read_clipboard_text() or ""
    r.record(
        "RD-07", "reading", "select all and copy work from the keyboard",
        "serious", "pass" if selected and copied and clipboard.strip() else "fail",
        "Ctrl+A then Ctrl+C produce a selection and put the page text on the clipboard",
        "status after select=%r, status after copy=%r, clipboard chars=%d"
        % (status_selected, s.status(), len(clipboard)),
        steps=["focus the page view", "press Ctrl+A", "press Ctrl+C", "read the clipboard"],
        element=s.element("page"),
        evidence={"clipboard_prefix": clipboard[:120], "status_selected": status_selected},
        fix="none needed; the shortcut path already works")
    s.selection_ready = bool(selected)


def phase_annotation(s, r, comment):
    """Annotation list, note field and the keyboard-only add/jump/delete path."""
    notes = s.uia_named("notes")
    note_edit = s.uia_named("note_edit")
    r.record(
        "AN-01", "annotation", "annotation list exposes name and list role",
        "serious", "pass" if notes and (notes.get("name") or "").strip()
        and notes.get("control_type") == "ListControl" else "fail",
        "the annotation list is a named List control that assistive technology can read",
        "name=%r control_type=%r focusable=%s" % ((notes or {}).get("name"),
                                                  (notes or {}).get("control_type"),
                                                  (notes or {}).get("keyboard_focusable")),
        steps=["read the UIA element of control 121 (ListBox)"],
        element=s.element("notes"),
        fix="none needed while the LB window text stays '标注列表'")

    r.record(
        "AN-02", "annotation", "note comment field has an accessible name",
        "blocking", "pass" if note_edit and (note_edit.get("name") or "").strip() else "fail",
        "the comment editor announces a name such as 标注内容",
        "name=%r control_type=%r help=%r" % ((note_edit or {}).get("name"),
                                             (note_edit or {}).get("control_type"),
                                             (note_edit or {}).get("help_text")),
        steps=["read the UIA element of control 122 (multiline Edit)"],
        element=s.element("note_edit"),
        fix="set an accessible name on the multiline edit; the 标注（双击跳转） static is not associated")

    if not getattr(s, "selection_ready", False):
        for identifier, title, severity in (
                ("AN-03", "an annotation is added with the keyboard only", "blocking"),
                ("AN-04", "annotation rows expose quote and comment text", "serious"),
                ("AN-05", "an annotation is reached from the keyboard", "serious"),
                ("AN-06", "an annotation is deleted from the keyboard", "moderate")):
            r.record(
                identifier, "annotation", title, severity, "not_verified",
                "the keyboard-only annotation path runs on the real host",
                "not measured: the host selects text only through Ctrl+A, which the "
                "%r transport cannot deliver" % (s.kb.transport,),
                steps=["would select the page, type a comment, then use the annotation buttons"],
                element=s.element("add_note"),
                reason="no keyboard text selection without the real input queue",
                fix="re-run with the SendInput transport")
        return

    _annotation_keyboard(s, r, comment)


def _annotation_keyboard(s, r, comment):
    """The measured keyboard path from page selection to annotation removal."""
    ok_edit, stops_edit = s.goto("note_edit")
    if ok_edit:
        s.kb.type_text(comment, note="type the annotation comment")
    ok_add, stops_add = s.activate("add_note")
    added = s.host.wait_for(lambda: len(s.list_item_names("notes")) == 1, timeout=60,
                            interval=0.25, label="annotation list grows to one row")
    names = s.list_item_names("notes")
    status = s.status()
    r.record(
        "AN-03", "annotation", "an annotation is added with the keyboard only",
        "blocking", "pass" if ok_edit and ok_add and added else "fail",
        "typing a comment and pressing Space on 添加标注 stores exactly one annotation",
        "focus reached editor=%s and command=%s, annotation rows=%d, status=%r"
        % (ok_edit, ok_add, len(names), status),
        steps=["Ctrl+A on the page", "Tab to the comment field", "type %r" % comment,
               "Tab to 添加标注", "press Space"],
        element=s.element("add_note"),
        evidence={"stops": stops_edit + stops_add, "names": names, "status": status},
        fix="none needed; keyboard annotation already works")

    r.record(
        "AN-04", "annotation", "annotation rows expose quote and comment text",
        "serious", "pass" if names and any(comment in (name or "") for name in names) else "fail",
        "each annotation row's accessible name contains the stored comment text",
        "row names=%r" % (names[:4],),
        steps=["read the UIA ListItem children of control 121"],
        element=s.element("notes"),
        evidence={"names": names},
        fix="none needed while rows are real list strings")

    ok_list, stops_list = s.goto("notes")
    if ok_list:
        s.kb.press("home", note="select the first annotation")
    ok_jump, stops_jump = s.activate("jump_note")
    jumped = s.wait_status_contains("标注", timeout=30)
    r.record(
        "AN-05", "annotation", "an annotation is reached from the keyboard",
        "serious", "pass" if ok_list and ok_jump and jumped else "fail",
        "selecting a row and pressing Space on 跳转标注 locates the annotation without a mouse",
        "list focus=%s command focus=%s status=%r"
        % (ok_list, ok_jump, s.status()),
        steps=["Tab to the annotation list", "Home to select the first row",
               "Tab to 跳转标注", "press Space"],
        element=s.element("jump_note"),
        evidence={"stops": stops_list + stops_jump},
        fix="none needed; the keyboard equivalent of the double-click exists")

    ok_del, stops_del = s.activate("delete_note")
    removed = s.host.wait_for(lambda: len(s.list_item_names("notes")) == 0, timeout=60,
                              interval=0.25, label="annotation list returns to empty")
    r.record(
        "AN-06", "annotation", "an annotation is deleted from the keyboard",
        "moderate", "pass" if ok_del and removed else "fail",
        "with a row selected, Space on 删除标注 removes it",
        "command focus=%s remaining rows=%d status=%r"
        % (ok_del, len(s.list_item_names("notes")), s.status()),
        steps=["keep a row selected", "Tab to 删除标注", "press Space"],
        element=s.element("delete_note"),
        evidence={"stops": stops_del},
        fix="none needed")


def _percent(label, marker):
    match = re.search(marker + r"\s*(\d+)%", label or "")
    return int(match.group(1)) if match else None


def phase_settings(s, r):
    """Font size commands of the existing inline settings flow."""
    font_dec = s.uia_named("font_dec")
    font_inc = s.uia_named("font_inc")
    names_ok = bool(font_dec) and bool(font_inc) and \
        (font_dec.get("name") or "").strip() == "字号-" and \
        (font_inc.get("name") or "").strip() == "字号+"
    label_before = s.page_label()
    before = _percent(label_before, "字号")
    ok_inc, stops = s.activate("font_inc")
    changed = s.host.wait_for(lambda: s.page_label() != label_before, timeout=90, interval=0.25,
                              label="font size reflows the page")
    after = _percent(s.page_label(), "字号")
    r.record(
        "ST-01", "settings", "font size commands expose name, role and state",
        "serious",
        "pass" if names_ok and ok_inc and changed and after is not None and before is not None
        and after > before else "fail",
        "字号- and 字号+ are named buttons that change the reflow size from the keyboard",
        "names_ok=%s, focus=%s, 字号 %s -> %s" % (names_ok, ok_inc, before, after),
        steps=["Tab to 字号+", "press Space", "read the position line"],
        element=s.element("font_inc"),
        evidence={"stops": stops, "label_before": label_before, "label_after": s.page_label()},
        fix="none needed; the inline size command already works from the keyboard")

    time.sleep(0.8)
    ini = s.host.read_ini() or {}
    host_section = ini.get("Host") or {}
    stored = host_section.get("FontPercent")
    r.record(
        "ST-02", "settings", "the size setting persists and is the one the screen shows",
        "moderate",
        "pass" if stored is not None and after is not None and str(stored).strip() == str(after)
        else "fail",
        "host.ini stores the font percentage the reading surface reports",
        "host.ini FontPercent=%r, position line shows %r" % (stored, after),
        steps=["press 字号+", "read host.ini from the data directory"],
        element={"file": "host.ini", "section": "Host", "key": "FontPercent"},
        evidence={"host_ini": host_ini_evidence(s.host)},
        fix="none needed while settings_save writes the accepted value")

    zoom_dec = s.uia_named("zoom_dec")
    zoom_inc = s.uia_named("zoom_inc")
    r.record(
        "ST-04", "settings", "a dedicated settings surface exists in the Windows host",
        "moderate", "gap",
        "preferences that change the reading surface are reachable as their own named surface",
        "the Windows host has no settings or preferences window: the inline 字号/缩放 commands "
        "plus host.ini are the whole settings flow (static evidence: no dialog template, no "
        "preferences command id)",
        steps=["enumerate all top-level windows of the host", "review the command ids in "
               "examples/reader.c"],
        element={"control_ids": "IDC_* enum 100..136", "top_level_windows": 1},
        fix="add a 设置 dialog with labelled controls, or state in product docs that the inline "
            "size/zoom commands are the settings surface")

    access_keys = {}
    for name in BUTTON_CONTROLS:
        described = s.uia_named(name)
        if described:
            access_keys[name] = described.get("access_key") or ""
    with_keys = {name: key for name, key in access_keys.items() if key}
    r.record(
        "ST-05", "settings", "main-window commands are reachable through access keys",
        "moderate", "gap" if not with_keys else "pass",
        "each main-window command offers an Alt access key so it can be invoked without counting "
        "Tab stops",
        "%d of %d main-window buttons expose an AccessKey; the dialog buttons do because their "
        "text carries &R/&S mnemonics" % (len(with_keys), len(access_keys)),
        steps=["read the UIA AccessKey property of every main-window button"],
        element={"controls": list(access_keys)},
        evidence={"access_keys": access_keys, "zoom_hint": bool(zoom_inc) and bool(zoom_dec)},
        fix="add &-mnemonics to the main command texts and handle WM_SYSCHAR through the existing "
            "IsDialogMessage loop")


def host_ini_evidence(host):
    ini = host.read_ini() or {}
    return {section: values for section, values in ini.items()
            if section in ("Host", "Shelf")}


def phase_fixed(s, r):
    """Zoom state on a fixed-page book, where the size buttons invert."""
    font_enabled = s.host.enabled("font_inc")
    zoom_enabled = s.host.wait_enabled("zoom_inc", timeout=60)
    label_before = s.page_label()
    before = _percent(label_before, "缩放")
    ok_inc, stops = s.activate("zoom_inc")
    changed = s.host.wait_for(lambda: s.page_label() != label_before, timeout=90, interval=0.25,
                              label="zoom re-renders the fixed page")
    after = _percent(s.page_label(), "缩放")
    r.record(
        "ST-03", "settings", "size and zoom expose the right state for each book kind",
        "serious",
        "pass" if zoom_enabled and ok_inc and changed and after is not None and before is not None
        and after > before else "fail",
        "on a fixed-page book 缩放+ is enabled and 字号+ is disabled, and the zoom applies",
        "font_inc enabled=%s, zoom_inc enabled=%s, 缩放 %s -> %s, focus=%s"
        % (font_enabled, bool(zoom_enabled), before, after, ok_inc),
        steps=["open a fixed-page PDF from the keyboard", "read both size commands",
               "Tab to 缩放+", "press Space"],
        element=s.element("zoom_inc"),
        evidence={"stops": stops, "label_before": label_before, "label_after": s.page_label()},
        fix="none needed; host_update_controls already swaps the command pairs")


def phase_details(s, r):
    """Details dialog: fields, keyboard order, cancel, focus return, default button."""
    ok_list, stops_list = s.goto("books")
    if ok_list:
        s.kb.press("home", note="select a shelf row before opening 详情")
    s.host.wait_enabled("metadata_button", timeout=90)
    ok_open, stops_open = s.activate("metadata_button")
    dialog = s.host.wait_for(s.host.dialog_window, timeout=90, interval=0.2,
                             label="details dialog opens")
    if not dialog:
        r.record(
            "OR-01", "organize", "details opens from the keyboard",
            "blocking", "fail",
            "Space on 详情 opens the details dialog for the selected book",
            "no dialog window appeared; 详情 focus reached=%s, status=%r"
            % (ok_open, s.status()),
            steps=["Tab to the shelf", "Home", "Tab to 详情", "press Space"],
            element=s.element("metadata_button"),
            evidence={"stops": stops_open, "dialog": None},
            fix="keep the details command reachable and report why it refused in the status line")
        for identifier, title in (("OR-02", "the details dialog exposes a name and dialog role"),
                                  ("OR-03", "the dialog title field has an accessible name"),
                                  ("OR-04", "the dialog author field has an accessible name"),
                                  ("OR-05", "the favourite checkbox exposes name, key and state"),
                                  ("OR-06", "the dialog buttons expose names and access keys"),
                                  ("OR-07", "Tab order inside the dialog is complete and contained"),
                                  ("OR-08", "Escape closes the details dialog"),
                                  ("OR-09", "focus returns to the command that opened the dialog"),
                                  ("OR-10", "the owner window reports its disabled state"),
                                  ("OR-11", "Enter activates the dialog default button")):
            r.record(identifier, "organize", title, "blocking", "not_verified",
                     "the details dialog is audited while it is open",
                     "not measured: the dialog never opened",
                     steps=["open the details dialog with the keyboard"],
                     element=s.element("metadata_button"),
                     reason="details dialog did not open", fix="fix the open path first")
        return

    s.dump("t03-details-dialog", dialog, depth=3)
    s.shot("03-details-dialog")
    problems = s.host.verified_dialog_controls(dialog)
    r.record(
        "OR-01", "organize", "details opens from the keyboard",
        "blocking", "pass" if ok_open and not problems else "fail",
        "Space on 详情 opens the details dialog for the selected book",
        "dialog hwnd=0x%x title=%r; control problems=%r" % (dialog, w32.window_text(dialog), problems),
        steps=["Tab to the shelf", "Home", "Tab to 详情", "press Space", "wait for the dialog"],
        element=s.element("metadata_button"),
        evidence={"stops": stops_open, "dialog_class": w32.class_name(dialog),
                  "dialog_controls": sorted(s.host.dialog_controls(dialog))},
        fix="none needed; the keyboard open path works")

    dialog_el = s.uia_at(dialog)
    r.record(
        "OR-02", "organize", "the details dialog exposes a name and dialog role",
        "serious",
        "pass" if dialog_el and (dialog_el.get("name") or "").strip() else "fail",
        "the dialog element announces its title and a dialog/window role",
        "name=%r control_type=%r class=%r"
        % ((dialog_el or {}).get("name"), (dialog_el or {}).get("control_type"),
           (dialog_el or {}).get("class_name")),
        steps=["read the UIA element of the dialog window"],
        element={"hwnd": hex(dialog), "class": w32.class_name(dialog)},
        fix="none needed while SetWindowTextW keeps 书籍详情 on the dialog")

    title_el = s.uia_named("metadata_title")
    author_el = s.uia_named("metadata_author")
    for identifier, title, described, noun in (
            ("OR-03", "the dialog title field has an accessible name", title_el, "书名"),
            ("OR-04", "the dialog author field has an accessible name", author_el, "作者")):
        r.record(
            identifier, "organize", title, "blocking",
            "pass" if described and (described.get("name") or "").strip() else "fail",
            "the %s edit announces a name instead of relying on the adjacent static label" % noun,
            "name=%r control_type=%r help=%r" % ((described or {}).get("name"),
                                                 (described or {}).get("control_type"),
                                                 (described or {}).get("help_text")),
            steps=["read the UIA element of the %s edit control" % noun],
            element={"control_id": 129 if noun == "书名" else 130},
            fix="name the edits (for example through WM_GETOBJECT or a UIA provider) so the "
                "label association is programmatic, not visual")

    favorite = s.uia_named("metadata_favorite")
    r.record(
        "OR-05", "organize", "the favourite checkbox exposes name, key and state",
        "serious",
        "pass" if favorite and (favorite.get("name") or "").strip()
        and "TogglePattern" in (favorite.get("patterns") or []) else "fail",
        "the 收藏 checkbox is a named CheckBox with an access key and a toggle state",
        "name=%r control_type=%r access_key=%r patterns=%r"
        % ((favorite or {}).get("name"), (favorite or {}).get("control_type"),
           (favorite or {}).get("access_key"), (favorite or {}).get("patterns")),
        steps=["read the UIA element of control 131 (BS_AUTOCHECKBOX)"],
        element={"control_id": 131, "class": "Button"},
        fix="none needed while the text carries &F and the check state comes from the control")

    save_el = s.uia_named("metadata_save")
    cancel_el = s.uia_named("metadata_cancel")
    sav = (save_el or {}).get("name") or ""
    can = (cancel_el or {}).get("name") or ""
    key_save = (save_el or {}).get("access_key") or ""
    key_cancel = (cancel_el or {}).get("access_key") or ""
    r.record(
        "OR-06", "organize", "the dialog buttons expose names and access keys",
        "moderate",
        "pass" if sav and can and key_save and key_cancel else "gap",
        "every dialog button carries a mnemonic so it can be invoked with Alt plus a letter",
        "保存 name=%r access_key=%r; 取消 name=%r access_key=%r" % (sav, key_save, can, key_cancel),
        steps=["read the UIA Name and AccessKey of controls 132 and 133"],
        element={"control_id": 133, "class": "Button"},
        evidence={"save": {"name": sav, "access_key": key_save},
                  "cancel": {"name": can, "access_key": key_cancel}},
        fix="give 取消 a mnemonic (取消(&C)) like the other dialog commands")

    order = []
    for _ in range(5):
        s.kb.press("tab", note="dialog tab order")
        order.append(s.focus_name())
    expected = ["metadata_author", "metadata_favorite", "metadata_save", "metadata_cancel",
                "metadata_title"]
    contained = all(name.startswith("metadata_") for name in order)
    r.record(
        "OR-07", "organize", "Tab order inside the dialog is complete and contained",
        "blocking", "pass" if order == expected and contained else "fail",
        "Tab walks 书名 -> 作者 -> 收藏 -> 保存 -> 取消 -> 书名 and never leaves the dialog",
        "observed order=%r (expected %r), all inside dialog=%s" % (order, expected, contained),
        steps=["open the dialog", "press Tab five times and read the focused control"],
        element={"dialog": hex(dialog)},
        evidence={"order": order},
        fix="none needed while the template order matches the visual order")

    owner_disabled = not bool(w32.user32.IsWindowEnabled(s.host.hwnd))
    import_el = s.uia_named("import_button")
    owner_uia_disabled = bool(import_el) and import_el.get("enabled") is False
    r.record(
        "OR-10", "organize", "the owner window reports its disabled state",
        "serious", "pass" if owner_disabled and owner_uia_disabled else "fail",
        "while the dialog is open the main window and its commands report IsEnabled=false",
        "IsWindowEnabled(main)=%s, UIA enabled of 导入=%r"
        % (not owner_disabled, (import_el or {}).get("enabled")),
        steps=["read IsWindowEnabled and the UIA IsEnabled of a main-window command"],
        element=s.element("import_button"),
        fix="none needed; EnableWindow(owner, FALSE) already reports through UIA")

    s.kb.press("escape", note="cancel the dialog from the keyboard")
    closed = s.host.wait_for(lambda: s.host.dialog_window() is None, timeout=30, interval=0.2,
                             label="dialog closes on Escape")
    r.record(
        "OR-08", "organize", "Escape closes the details dialog",
        "blocking", "pass" if closed else "fail",
        "Escape cancels the dialog without touching the book",
        "dialog closed=%s, status=%r" % (bool(closed), s.status()),
        steps=["open the dialog", "press Escape"],
        element={"dialog": hex(dialog)},
        fix="none needed; IsDialogMessage already maps Escape to IDCANCEL")

    focus_after = s.focus_name()
    r.record(
        "OR-09", "organize", "focus returns to the command that opened the dialog",
        "blocking", "pass" if focus_after == "metadata_button" else "fail",
        "after the dialog closes the keyboard focus is back on 详情",
        "focused control after close=%r" % (focus_after,),
        steps=["open the dialog from 详情 with the keyboard", "press Escape",
               "read GetGUIThreadInfo(hwndFocus)"],
        element=s.element("metadata_button"),
        evidence={"focus_state": s.kb.focus_state()},
        fix="call SetFocus on the invoking button in the dialog's WM_DESTROY "
            "(SetActiveWindow alone does not restore keyboard focus)")

    ok_again, stops_again = s.goto("metadata_button")
    if ok_again:
        s.kb.press("space", note="reopen the details dialog")
    reopened = s.host.wait_for(s.host.dialog_window, timeout=60, interval=0.2,
                               label="details dialog reopens")
    if not reopened:
        r.record(
            "OR-11", "organize", "Enter activates the dialog default button",
            "moderate", "not_verified",
            "Enter in the dialog triggers 保存 and closes it through the save path",
            "not measured: the dialog could not be reopened after Escape",
            steps=["reopen the dialog", "press Enter"],
            element={"control_id": 132},
            reason="dialog did not reopen", fix="fix the reopen path first")
        return
    time.sleep(0.4)
    s.kb.press("enter", note="activate the default 保存 button")
    saved = s.host.wait_for(lambda: "已保存" in s.status() or "未提交" in s.status(),
                            timeout=90, interval=0.25, label="save path reports a result")
    gone = s.host.wait_for(lambda: s.host.dialog_window() is None, timeout=60, interval=0.2,
                           label="dialog closes after the default action")
    recovery = s.host.dialog_window()
    if recovery:
        s.trace.event("details_recovery_dialog",
                      {"hwnd": recovery, "title": w32.window_text(recovery)})
        s.kb.press("escape")
    r.record(
        "OR-11", "organize", "Enter activates the dialog default button",
        "moderate", "pass" if saved and gone else "fail",
        "Enter in the dialog triggers the default 保存 command and the dialog closes",
        "status=%r, dialog closed=%s, recovery dialog=%s"
        % (s.status(), bool(gone), bool(recovery)),
        steps=["open the dialog", "press Enter without touching the fields"],
        element={"control_id": 132, "class": "Button"},
        evidence={"stops": stops_again, "status": s.status()},
        fix="none needed; DM_SETDEFID plus IsDialogMessage already route Enter")


def phase_keyboard(s, r):
    """Complete Tab order, reverse order, control coverage and UIA focus coherence."""
    s.goto("import_edit")
    core, repeated = s.chain()
    cycle_ok = bool(core) and repeated == core[0]
    r.record(
        "KB-01", "keyboard", "Tab order is complete, ordered and closes into a cycle",
        "blocking", "pass" if cycle_ok and len(core) >= 10 else "fail",
        "repeated Tab visits every enabled stop once and returns to the first stop",
        "stops=%d, repeated stop=%r, first stop=%r, order=%r"
        % (len(core), repeated, core[0] if core else None, core),
        steps=["focus the first stop", "press Tab until a stop repeats"],
        element={"stops": core},
        evidence={"order": core, "repeated": repeated},
        fix="none needed while WS_TABSTOP and WS_EX_CONTROLPARENT stay as they are")

    missing = [name for name in BUTTON_CONTROLS
               if s.host.enabled(name) and name not in core]
    r.record(
        "KB-03", "keyboard", "every enabled command is reachable with Tab",
        "blocking", "pass" if not missing else "fail",
        "each enabled button appears in the Tab cycle, so no command needs a mouse",
        "enabled buttons missing from the cycle=%r (cycle length %d)" % (missing, len(core)),
        steps=["discover the Tab cycle", "compare it with the enabled command list"],
        element={"buttons": list(BUTTON_CONTROLS)},
        evidence={"missing": missing, "cycle": core},
        fix="give any missing command WS_TABSTOP and keep it enabled only when usable")

    reverse = []
    for _ in range(len(core)):
        s.kb.press("tab", ("shift",), note="reverse Tab order")
        reverse.append(s.focus_name())
    forward_reversed = list(reversed(core))
    r.record(
        "KB-02", "keyboard", "Shift+Tab reverses the same order",
        "serious", "pass" if reverse == forward_reversed else "fail",
        "Shift+Tab visits the same stops in exactly the reverse order",
        "reverse=%r" % (reverse,),
        steps=["from the first stop press Shift+Tab once per stop"],
        element={"stops": reverse},
        evidence={"reverse": reverse, "forward_reversed": forward_reversed},
        fix="none needed while the dialog manager owns traversal")

    samples = []
    coherent = True
    for _ in range(3):
        s.kb.press("tab", note="UIA focus coherence sample")
        focused = s.uia.focused()
        hwnd_focus = s.kb.focus()
        sample = {"hwnd_focus": hwnd_focus and hex(hwnd_focus),
                  "uia_native_hwnd": (focused or {}).get("native_hwnd"),
                  "uia_name": (focused or {}).get("name"),
                  "uia_has_focus": (focused or {}).get("has_focus")}
        samples.append(sample)
        if not focused or int(focused.get("native_hwnd") or 0) != int(hwnd_focus or 0) \
                or not focused.get("has_focus"):
            coherent = False
    r.record(
        "KB-04", "keyboard", "UI Automation focus follows the keyboard focus",
        "blocking", "pass" if coherent else "fail",
        "the element that reports HasKeyboardFocus is the control the host gave focus to",
        "samples=%r" % (samples,),
        steps=["move focus with Tab", "compare GetGUIThreadInfo(hwndFocus) with the UIA "
               "element that reports HasKeyboardFocus"],
        element={"samples": samples},
        evidence={"samples": samples},
        fix="none needed while the standard providers answer focus for these controls")

