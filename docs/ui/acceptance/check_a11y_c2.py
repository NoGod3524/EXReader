#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""C2 accessibility acceptance: UIA text, control names, Tab order, focus ring,
no page border, high contrast. One real window, real keystrokes (SendInput).

Usage: check_a11y_c2.py EXE FONT BOOK OUT [--no-contrast]

Rules (docs/ui acceptance conventions):
 - every key is a real SendInput keystroke, never a posted message;
 - the window is brought to the foreground ONCE, logged before the call; if the
   system refuses, the run stops with "无法获得前台" and does not retry;
 - pixel comparison is client area only, with a negative example (--self-test).
High contrast is switched through the real system setting and restored in a
finally block; the previous state is read back and recorded.
"""
import ctypes as C
from ctypes import wintypes as W
import json
import hashlib
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from PIL import Image, ImageDraw  # noqa: E402
import comtypes  # noqa: E402
import comtypes.client  # noqa: E402

comtypes.client.GetModule('UIAutomationCore.dll')
from comtypes.gen import UIAutomationClient as UC  # noqa: E402
from capture_window import capture, U  # noqa: E402

U.SetForegroundWindow.argtypes = [W.HWND]
U.GetGUIThreadInfo.argtypes = [W.DWORD, C.c_void_p]
U.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
U.GetDlgCtrlID.argtypes = [W.HWND]
U.GetAsyncKeyState.argtypes = [C.c_int]
U.MapVirtualKeyW.argtypes = [W.UINT, W.UINT]

VK = dict(TAB=0x09, RETURN=0x0D, ESCAPE=0x1B, SPACE=0x20, PRIOR=0x21, NEXT=0x22, END=0x23, HOME=0x24,
          LEFT=0x25, UP=0x26, RIGHT=0x27, DOWN=0x28, SHIFT=0x10, CONTROL=0x11, A=0x41, F=0x46)
EXTENDED = {VK[k] for k in ('PRIOR', 'NEXT', 'END', 'HOME', 'LEFT', 'UP', 'RIGHT', 'DOWN')}
FOREGROUND_PID = None


class KEYBDINPUT(C.Structure):
    _fields_ = [('wVk', W.WORD), ('wScan', W.WORD), ('dwFlags', W.DWORD), ('time', W.DWORD), ('dwExtraInfo', C.c_size_t)]


class MOUSEINPUT(C.Structure):
    _fields_ = [('dx', C.c_long), ('dy', C.c_long), ('mouseData', W.DWORD), ('dwFlags', W.DWORD), ('time', W.DWORD),
                ('dwExtraInfo', C.c_size_t)]


class INPUT(C.Structure):
    class _U(C.Union):
        _fields_ = [('ki', KEYBDINPUT), ('mi', MOUSEINPUT)]
    _anonymous_ = ('u',)
    _fields_ = [('type', W.DWORD), ('u', _U)]


U.SendInput.argtypes = [W.UINT, C.POINTER(INPUT), C.c_int]


def _send(vk, up):
    flags = (2 if up else 0) | (1 if vk in EXTENDED else 0)
    item = INPUT(type=1, ki=KEYBDINPUT(vk, U.MapVirtualKeyW(vk, 0), flags, 0, 0))
    assert U.SendInput(1, C.byref(item), C.sizeof(INPUT)) == 1, 'SendInput refused'


def press(name, ctrl=False, shift=False, settle=.35):
    """One real keystroke (optionally with Ctrl/Shift held)."""
    if FOREGROUND_PID is not None:
        found = W.DWORD()
        U.GetWindowThreadProcessId(U.GetForegroundWindow(), C.byref(found))
        assert found.value == FOREGROUND_PID, ('foreground was lost; refusing to send keys to another app '
                                                '(expected PID %d, actual PID %d)' % (FOREGROUND_PID, found.value))
    held = [VK['CONTROL']] if ctrl else []
    held += [VK['SHIFT']] if shift else []
    for k in held:
        _send(k, False)
    _send(VK[name], False)
    _send(VK[name], True)
    for k in reversed(held):
        _send(k, True)
    # UIA callbacks are delivered to this client's STA; sleeping loses events.
    comtypes.client.PumpEvents(settle)


class Run:
    def __init__(self, exe, font, book, out):
        self.exe, self.font, self.book, self.out = exe, font, book, out
        out.mkdir(parents=True, exist_ok=True)
        self.iua = comtypes.CoCreateInstance(UC.CUIAutomation._reg_clsid_, interface=UC.IUIAutomation,
                                             clsctx=comtypes.CLSCTX_INPROC_SERVER)
        self.events = []
        self.log = []

    # -- process ---------------------------------------------------------
    def start(self):
        profile = Path(tempfile.mkdtemp(prefix='a11y_c2_'))
        (profile / 'host.ini').write_text('[Host]\nWindowWidth=1280\nWindowHeight=860\nShellTheme=0\nShellFont=18\n')
        self.proc = subprocess.Popen([str(self.exe), '--data', str(profile), '--font', str(self.font), str(self.book)])
        from check_shell_2a import main_window
        end = time.monotonic() + 60
        self.hwnd = 0
        while time.monotonic() < end and not self.hwnd:
            time.sleep(.5)
            self.hwnd = main_window(self.proc.pid)
        assert self.hwnd, 'host window did not appear'
        self.root = self.iua.ElementFromHandle(self.hwnd)
        while time.monotonic() < end:  # the reading screen is up once the document element exists
            if self.find(automation_id='IDC_PAGE'):
                break
            time.sleep(.5)
        assert self.find(automation_id='IDC_PAGE'), 'book did not reach the reading screen'
        time.sleep(3)
        self.tid = U.GetWindowThreadProcessId(self.hwnd, None)

    def activate_once(self):
        print('activating window for focus checks', flush=True)
        self.log.append('activating window for focus checks')
        U.ShowWindow(self.hwnd, 9)
        # One attempt only, through UI Automation's own SetFocus: it activates the top-level
        # window with the privileges of the accessibility service, and sends no key or click.
        self.root.SetFocus()
        time.sleep(.8)
        found = W.DWORD()
        U.GetWindowThreadProcessId(U.GetForegroundWindow(), C.byref(found))
        if found.value != self.proc.pid:
            print('无法获得前台', flush=True)
            raise SystemExit('无法获得前台')

    # -- UIA ------------------------------------------------------------
    def find(self, automation_id=None, name=None, class_name=None):
        for row in self.dump(quiet=True):
            if automation_id and row['id'] != automation_id:
                continue
            if name and row['name'] != name:
                continue
            if class_name and row['class'] != class_name:
                continue
            return row
        return None

    def element(self, **kw):
        want = self.find(**kw)
        if not want:
            return None
        found = self.root.FindAll(7, self.iua.CreateTrueCondition())
        for i in range(found.Length):
            e = found.GetElement(i)
            if e.CurrentAutomationId == want['id'] and e.CurrentName == want['name'] and e.CurrentClassName == want['class']:
                return e
        return None

    def dump(self, quiet=False):
        rows = []
        found = self.root.FindAll(7, self.iua.CreateTrueCondition())
        for i in range(found.Length):
            e = found.GetElement(i)
            kind = e.CurrentLocalizedControlType
            ctype = e.CurrentControlType
            rect = e.CurrentBoundingRectangle
            rows.append(dict(name=e.CurrentName, type=kind, type_id=ctype, id=e.CurrentAutomationId,
                             **{'class': e.CurrentClassName}, enabled=bool(e.CurrentIsEnabled),
                             help=e.CurrentHelpText, focusable=bool(e.CurrentIsKeyboardFocusable),
                             focused=bool(e.CurrentHasKeyboardFocus), control=bool(e.CurrentIsControlElement),
                             offscreen=bool(e.CurrentIsOffscreen), rect=[rect.left, rect.top, rect.right, rect.bottom]))
        return rows

    def page_text(self, count=50):
        page = self.element(automation_id='IDC_PAGE')
        if not page:
            return None
        pattern = page.GetCurrentPattern(10014).QueryInterface(UC.IUIAutomationTextPattern)
        try:
            return pattern.DocumentRange.GetText(count)
        except comtypes.COMError as error:
            return None if error.args[0] in (-2147220991,) else '<COMError %x>' % (error.args[0] & 0xffffffff)

    def focus_state(self):
        class GUITHREADINFO(C.Structure):
            _fields_ = [('cbSize', W.DWORD), ('flags', W.DWORD), ('hwndActive', W.HWND), ('hwndFocus', W.HWND),
                        ('hwndCapture', W.HWND), ('hwndMenuOwner', W.HWND), ('hwndMoveSize', W.HWND),
                        ('hwndCaret', W.HWND), ('rcCaret', W.RECT)]
        info = GUITHREADINFO()
        info.cbSize = C.sizeof(info)
        U.GetGUIThreadInfo(self.tid, C.byref(info))
        hwnd = info.hwndFocus
        if not hwnd:
            return dict(hwnd=0, label='(none)')
        name = C.create_unicode_buffer(64)
        U.GetClassNameW(hwnd, name, 64)
        ident = U.GetDlgCtrlID(hwnd)
        try:
            e = self.iua.ElementFromHandle(hwnd)
            uia = e.CurrentName
        except comtypes.COMError:
            uia = '?'
        label = '%s#%d "%s"' % (name.value, ident, uia)
        if name.value == 'EXReaderPage':
            label = 'EXReaderPage "%s"' % uia
        return dict(hwnd=hwnd, cls=name.value, ctl=ident, name=uia, label=label)

    def tab_to(self, name):
        """Reach a verified focus stop with real Tab keys, bounded to one lap."""
        for _ in range(64):
            state = self.focus_state()
            if state.get('name') == name:
                return state
            press('TAB', settle=.15)
        raise AssertionError('Tab cannot reach ' + name)

    # -- events ---------------------------------------------------------
    def listen(self):
        run = self

        class Auto(comtypes.COMObject):
            _com_interfaces_ = [UC.IUIAutomationEventHandler]

            def HandleAutomationEvent(self, sender, event_id):
                try:
                    run.events.append(('automation', int(event_id), sender.CurrentName, time.monotonic()))
                except comtypes.COMError:
                    run.events.append(('automation', int(event_id), '?', time.monotonic()))

        class Structure(comtypes.COMObject):
            _com_interfaces_ = [UC.IUIAutomationStructureChangedEventHandler]

            def HandleStructureChangedEvent(self, sender, change, runtime_id):
                try:
                    run.events.append(('structure', int(change), sender.CurrentName, time.monotonic()))
                except comtypes.COMError:
                    run.events.append(('structure', int(change), '?', time.monotonic()))

        self._h = (Auto(), Structure())
        self.iua.AddAutomationEventHandler(20015, self.root, 7, None, self._h[0])  # Text_TextChanged
        self.iua.AddAutomationEventHandler(20014, self.root, 7, None, self._h[0])  # Text_TextSelectionChanged
        self.iua.AddStructureChangedEventHandler(self.root, 7, None, self._h[1])

    def mark(self):
        return len(self.events)

    def since(self, mark):
        names = {20015: 'TextChanged', 20014: 'TextSelectionChanged'}
        kinds = {0: 'ChildAdded', 1: 'ChildRemoved', 2: 'ChildrenInvalidated', 3: 'ChildrenBulkAdded',
                 4: 'ChildrenBulkRemoved', 5: 'ChildrenReordered'}
        out = []
        for kind, code, who, _ in self.events[mark:]:
            out.append('%s(%s) on "%s"' % (names.get(code, code) if kind == 'automation' else 'StructureChanged',
                                           '' if kind == 'automation' else kinds.get(code, code), who))
        return out

    # -- capture -----------------------------------------------------------
    def shot(self, name):
        path = self.out / (name + '.png')
        meta = capture(self.proc.pid, path)
        return path, meta


def accent_ring_width(image, box, accent):
    """Longest run of accent-coloured pixels along the box's middle row and column."""
    left, top, right, bottom = box
    best = 0
    def run(points):
        longest = current = 0
        for p in points:
            near = all(abs(a - b) <= 40 for a, b in zip(image.getpixel(p)[:3], accent))
            current = current + 1 if near else 0
            longest = max(longest, current)
        return longest
    mid_y, mid_x = (top + bottom) // 2, (left + right) // 2
    best = max(run((x, mid_y) for x in range(left, right)), run((mid_x, y) for y in range(top, bottom)))
    return best


def region_diff(a, b, box):
    """Number of differing pixels (any channel) inside box; no getbbox() shortcut."""
    left, top, right, bottom = box
    ca, cb = a.convert('RGBA').crop(box).tobytes(), b.convert('RGBA').crop(box).tobytes()
    return sum(1 for i in range(0, len(ca), 4) if ca[i:i + 4] != cb[i:i + 4])


def self_test():
    """Negative example: a 2px page border drawn on a copy MUST be counted."""
    base = Image.new('RGB', (400, 300), (245, 245, 242))
    plain = base.copy()
    bordered = base.copy()
    ImageDraw.Draw(bordered).rectangle((1, 61, 398, 298), outline=(69, 83, 224), width=2)
    page = (0, 60, 400, 300)
    assert region_diff(base, plain, page) == 0
    assert region_diff(base, bordered, page) > 0
    return dict(identical=region_diff(base, plain, page), with_2px_border=region_diff(base, bordered, page))


def main():
    if sys.argv[1:] == ['--self-test']:
        print(json.dumps(self_test()))
        return
    exe, font, book, out = (Path(p).resolve() for p in sys.argv[1:5])
    contrast = '--no-contrast' not in sys.argv
    r = Run(exe, font, book, out)
    result = dict(exe=str(exe), font=str(font), book=str(book), self_test=self_test(),
                  sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in (exe, exe.with_name('libexreader.dll'), font, book, Path(__file__))})
    saved_contrast = None
    try:
        r.start()
        r.listen()
        r.activate_once()
        global FOREGROUND_PID
        FOREGROUND_PID = r.proc.pid
        # Activating the top-level HWND does not focus the custom text child.
        r.element(automation_id='IDC_PAGE').SetFocus()
        comtypes.client.PumpEvents(.5)
        assert r.focus_state().get('cls') == 'EXReaderPage', 'initial focus is not the page'
        result['foreground_activations'] = 1

        # A. names of the reading screen, everything closed
        closed = r.dump()
        (out / 'uia-closed.json').write_text(json.dumps(closed, ensure_ascii=False, indent=1), encoding='utf8')

        # B. read the page through UIA text pattern after real PageDown keys
        text, presses = None, 0
        mark = r.mark()
        while presses < 15 and not text:
            press('NEXT', settle=.6)
            presses += 1
            text = r.page_text(50)
        result['text_read'] = dict(pagedown_presses=presses, first50=text, length=len(text or ''),
                                   events=r.since(mark))
        assert text, 'UIA never returned page text'
        r.shot('01-text-page')

        # C. reading keys: PageDown / PageUp / End / Home (first 30 chars each time)
        keys = []
        for label, name, ext in (('PageDown', 'NEXT', 0), ('PageUp', 'PRIOR', 0), ('End', 'END', 0), ('Home', 'HOME', 0)):
            before = r.page_text(30)
            mark = r.mark()
            press(name, settle=.9)
            after = r.page_text(30)
            keys.append(dict(key=label, before=before, after=after, changed=before != after,
                             events=r.since(mark)))
        result['reading_keys'] = keys

        # A real selection must also reach UIA consumers.
        if not r.page_text():
            press('NEXT', settle=.8)
        mark = r.mark()
        press('A', ctrl=True, settle=.5)
        page = r.element(automation_id='IDC_PAGE')
        selection = page.GetCurrentPattern(10014).QueryInterface(UC.IUIAutomationTextPattern).GetSelection()
        result['selection'] = dict(ranges=selection.Length,
                                   first50=selection.GetElement(0).GetText(50) if selection.Length else '',
                                   events=r.since(mark))
        assert result['selection']['first50'], 'Ctrl+A did not select page text'
        press('ESCAPE')

        # D. Ctrl+F opens search, Esc returns to the page
        press('F', ctrl=True, settle=.8)
        search_focus = r.focus_state()
        search_open = r.dump()
        (out / 'uia-search-open.json').write_text(json.dumps(search_open, ensure_ascii=False, indent=1), encoding='utf8')
        # Tab order with the search bar open
        stops = [search_focus['label']]
        for _ in range(9):
            press('TAB')
            stops.append(r.focus_state()['label'])
        result['tab_with_search_open'] = stops
        press('ESCAPE', settle=.8)
        # focus after Esc may be the page or still inside the bar's host; record it
        result['search_esc_focus'] = r.focus_state()['label']
        result['search_ctrl_f_focus'] = search_focus['label']
        if r.focus_state().get('cls') != 'EXReaderPage':
            while r.focus_state().get('cls') != 'EXReaderPage':
                press('TAB')
                if len(r.log) > 40:
                    break
                r.log.append('realign')

        # E. Tab order, closed: from the page, one lap plus the Shift+Tab lap
        r.focus_state()
        order = [r.focus_state()['label']]
        for _ in range(6):
            press('TAB')
            order.append(r.focus_state()['label'])
        back = [order[-1]]
        for _ in range(6):
            press('TAB', shift=True)
            back.append(r.focus_state()['label'])
        result['tab_order_forward'] = order
        result['tab_order_backward'] = back
        # focus ring on 目录 and settings; page focused vs unfocused
        r.tab_to('阅读区域')
        page_focused = r.focus_state()
        pf_path, meta = r.shot('02-page-focused')
        press('TAB')
        toc_focus = r.focus_state()
        toc_path, _ = r.shot('03-toc-button-focused')
        press('TAB')
        set_focus = r.focus_state()
        set_path, _ = r.shot('04-settings-button-focused')
        assert [page_focused['name'], toc_focus['name'], set_focus['name']] == ['阅读区域', '目录', '设置']
        # return to the page for later steps
        while r.focus_state().get('cls') != 'EXReaderPage':
            press('TAB')
        result['focus_sequence_for_shots'] = [page_focused['label'], toc_focus['label'], set_focus['label']]

        dpi = meta['dpi']
        scale = dpi / 96.0
        client_left, client_top, cw, ch = meta['client_box']
        topbar = int(round(56 * scale))
        page_box = (client_left, client_top + topbar, client_left + cw, client_top + ch)
        imgs = {k: Image.open(p).convert('RGB') for k, p in (('page', pf_path), ('toc', toc_path), ('settings', set_path))}
        # page region with the page focused vs. the page NOT focused (toc/settings focused)
        result['page_border'] = dict(
            dpi=dpi, page_region=list(page_box),
            diff_page_focused_vs_toc_focused=region_diff(imgs['page'], imgs['toc'], page_box),
            diff_page_focused_vs_settings_focused=region_diff(imgs['page'], imgs['settings'], page_box),
            note='client area below the top bar only; 0 means no focus border is painted on the page')
        # focus ring width on the toc button (UIA rectangle in screen coords -> window coords)
        toc_element = r.element(automation_id='160')
        rect = toc_element.CurrentBoundingRectangle
        origin = (rect.left - meta['position'][0], rect.top - meta['position'][1],
                  rect.right - meta['position'][0], rect.bottom - meta['position'][1])
        accent = (0x45, 0x53, 0xe0)
        ring_on = accent_ring_width(imgs['toc'], origin, accent)
        ring_off = accent_ring_width(imgs['page'], origin, accent)
        result['focus_ring'] = dict(button='目录', box=list(origin), ring_px_when_focused=ring_on,
                                    ring_px_when_not_focused=ring_off, expected_px=round(2 * scale), accent='#4553E0',
                                    stroke_token='SHELL_FOCUS_STROKE=2px x dpi/96')
        # crop of the ring for the report
        pad = 12
        crop = imgs['toc'].crop((origin[0] - pad, origin[1] - pad, origin[2] + pad, origin[3] + pad))
        crop = crop.resize((crop.width * 4, crop.height * 4), Image.NEAREST)
        crop.save(out / '03b-toc-ring-crop-x4.png')

        # F. contents panel: open from the keyboard, list, jump, events
        press('TAB')  # page -> 目录
        mark = r.mark()
        press('SPACE', settle=1.2)  # native push buttons activate with Space
        toc_open = r.dump()
        (out / 'uia-toc-open.json').write_text(json.dumps(toc_open, ensure_ascii=False, indent=1), encoding='utf8')
        toc_focus_after_open = r.focus_state()['label']
        assert r.find(class_name='ListBox'), 'contents panel did not open'
        open_events = r.since(mark)
        r.shot('05-toc-open')
        stops = [toc_focus_after_open]
        for _ in range(4):
            press('TAB')
            stops.append(r.focus_state()['label'])
        result['tab_with_toc_open'] = stops
        # back to the list and jump
        while 'ListBox' not in r.focus_state().get('cls', ''):
            press('TAB')
            if len(r.log) > 60:
                break
            r.log.append('toc-realign')
        before = r.page_text(30)
        for _ in range(3):
            press('DOWN', settle=.25)
        mark = r.mark()
        press('RETURN', settle=1.8)
        after = r.page_text(30)
        result['toc_flow'] = dict(open_events=open_events, focus_after_open=toc_focus_after_open,
                                  text_before_jump=before, text_after_jump=after, changed=before != after,
                                  jump_events=r.since(mark), focus_after_jump=r.focus_state()['label'])

        # G. settings panel
        while r.focus_state().get('cls') != 'EXReaderPage':
            press('TAB')
            if len(r.log) > 90:
                break
            r.log.append('settings-realign')
        r.tab_to('设置')
        mark = r.mark()
        press('SPACE', settle=1.2)
        settings_open = r.dump()
        assert r.find(name='字号', class_name='Edit'), 'settings panel did not open'
        (out / 'uia-settings-open.json').write_text(json.dumps(settings_open, ensure_ascii=False, indent=1), encoding='utf8')
        result['settings_events'] = r.since(mark)
        r.shot('06-settings-open')
        stops = [r.focus_state()['label']]
        for _ in range(40):
            press('TAB', settle=.15)
            label = r.focus_state()['label']
            stops.append(label)
            if label == stops[0] or 'EXReaderPage' in label:
                break
        result['tab_with_settings_open'] = stops

        # H. coverage: every control element in every recorded state
        def controls(rows):
            keep = []
            skip = False
            for row in rows:
                if row['type_id'] == 50037:  # title bar and its caption buttons are the window frame
                    skip = True
                    continue
                if skip and row['class'] == '' and row['id'] == '' and row['type_id'] in (50000, 50009, 50011):
                    continue
                if row['control'] and not row['offscreen'] or row['focusable']:
                    keep.append(row)
            return keep
        coverage = {}
        for label, rows in (('closed', closed), ('search-open', search_open), ('toc-open', toc_open), ('settings-open', settings_open)):
            kept = [x for x in controls(rows) if x['class'] != 'EXReaderHost' and x['type_id'] != 50037]
            kept = [x for x in kept if x['name'] != 'System' and x['name'] not in ('Minimize', 'Maximize', 'Close', '最小化', '最大化', '关闭') or x['class']]
            coverage[label] = dict(total=len(kept), named=sum(1 for x in kept if x['name'].strip()),
                                   unnamed=[x for x in kept if not x['name'].strip()],
                                   with_help=sum(1 for x in kept if x['help'].strip()),
                                   controls=[dict(name=x['name'], type=x['type'], enabled=x['enabled'], help=x['help'],
                                                  id=x['id'], cls=x['class']) for x in kept])
        result['coverage'] = coverage
        press('ESCAPE', settle=.9)
        r.shot('07-after-settings')

        # I. high contrast, switched live through the system setting
        if contrast:
            class HC(C.Structure):
                _fields_ = [('cbSize', W.UINT), ('dwFlags', W.DWORD), ('lpszDefaultScheme', W.LPWSTR)]

            def get():
                h = HC()
                h.cbSize = C.sizeof(h)
                buf = C.create_unicode_buffer(256)
                h.lpszDefaultScheme = C.cast(buf, W.LPWSTR)
                assert U.SystemParametersInfoW(0x42, C.sizeof(h), C.byref(h), 0)
                return h.dwFlags, buf.value

            def put(flags, scheme):
                h = HC()
                h.cbSize = C.sizeof(h)
                h.dwFlags = flags
                h.lpszDefaultScheme = scheme
                return U.SystemParametersInfoW(0x43, C.sizeof(h), C.byref(h), 3)

            saved_contrast = get()
            assert not saved_contrast[0] & 1, 'high contrast already on; refusing to touch it'
            normal_window_color = U.GetSysColor(5)
            while r.focus_state().get('cls') != 'EXReaderPage':
                press('TAB')
                if len(r.log) > 140:
                    break
                r.log.append('hc-realign')
            put(saved_contrast[0] | 1, 'High Contrast Black')
            time.sleep(2.5)
            sys_window = U.GetSysColor(5)
            hc_state = dict(saved=dict(flags=saved_contrast[0], scheme=saved_contrast[1]),
                            sys_color_window=hex(sys_window), sys_color_window_normal=hex(normal_window_color),
                            sys_color_windowtext=hex(U.GetSysColor(8)), sys_color_hotlight=hex(U.GetSysColor(26)))
            hc_path, hc_meta = r.shot('08-high-contrast-text')
            r.tab_to('目录')
            hc_toc_path, _ = r.shot('09-high-contrast-toc-focus')
            press('SPACE', settle=1.2)
            assert r.find(class_name='ListBox'), 'high contrast contents panel did not open'
            hc_panel_path, _ = r.shot('10-high-contrast-toc-open')
            press('ESCAPE', settle=.8)
            r.tab_to('设置')
            press('SPACE', settle=1.2)
            assert r.find(name='字号', class_name='Edit'), 'high contrast settings panel did not open'
            hc_set_path, _ = r.shot('11-high-contrast-settings-open')
            press('ESCAPE', settle=.8)
            result['high_contrast'] = dict(hc_state, shots=[hc_path.name, hc_toc_path.name, hc_panel_path.name, hc_set_path.name])
        assert all(v['named'] == v['total'] for v in result['coverage'].values()), 'unnamed UIA controls'
        assert all(k['changed'] for k in result['reading_keys'][:2]), 'PageDown/PageUp did not change text'
        assert result['toc_flow']['changed'], 'contents jump did not change text'
        assert result['page_border']['diff_page_focused_vs_toc_focused'] == 0
        assert result['page_border']['diff_page_focused_vs_settings_focused'] == 0
        assert ring_on == result['focus_ring']['expected_px'] and ring_off == 0, 'focus ring pixels differ'
        assert any(event[0] == 'automation' and event[1] == 20015 for event in r.events), 'no TextChanged event'
        assert any(event[0] == 'automation' and event[1] == 20014 for event in r.events), 'no selection event'
        assert any(event[0] == 'structure' for event in r.events), 'no StructureChanged event'
        result['checks_passed'] = True
    finally:
        if saved_contrast is not None:
            h = HC()
            h.cbSize = C.sizeof(h)
            h.dwFlags = saved_contrast[0] & ~1
            h.lpszDefaultScheme = saved_contrast[1] or None
            U.SystemParametersInfoW(0x43, C.sizeof(h), C.byref(h), 3)
            time.sleep(2)
            buf = C.create_unicode_buffer(256)
            h2 = HC()
            h2.cbSize = C.sizeof(h2)
            h2.lpszDefaultScheme = C.cast(buf, W.LPWSTR)
            U.SystemParametersInfoW(0x42, C.sizeof(h2), C.byref(h2), 0)
            result['contrast_restored'] = dict(flags=h2.dwFlags, high_contrast_on=bool(h2.dwFlags & 1),
                                                sys_color_window=hex(U.GetSysColor(5)))
        try:
            r.iua.RemoveAllEventHandlers()
            r.proc.kill()
            r.proc.wait(timeout=10)
        except Exception:
            pass
        (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding='utf8')
    print(json.dumps(result, ensure_ascii=False, indent=1, default=str)[:6000])


if __name__ == '__main__':
    main()
