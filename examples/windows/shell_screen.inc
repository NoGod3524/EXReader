/* SPDX-License-Identifier: MIT */
/* 2a step 2: the reading screen of the Windows shell (EXR_READER_WINDOWS_SHELL).
   Included once by examples/reader.c, after create_controls and before
   layout_controls; it uses the host state `g` from there.

   Once a book is open the window shows the flat top bar (UI-SPEC, 2026-11-05):
   56 high, DeckMark surface with a line-token hairline on its last row, the title on the left
   (15, weight 650) and two 32x32 rounded icon buttons on the right (目录, 设置).
   Below it the page fills the window with no 3D edge.
   The back button, Esc without selection, Ctrl+W and Alt+Left return
   to the bookshelf. The acceptance build uses the same screen routing. Included after
   create_controls, so create_controls calls shell_create through a forward
   declaration.

   The buttons stay real BUTTON windows (BS_OWNERDRAW): their UIA proxies keep
   the name, role and Invoke, while every pixel is drawn here. In this step
   settings opens the owner-drawn child panel. */
#include "shell_tokens.h"

/* Every command ID routed through the main window or the settings panel, in
   one table: both end in shell_settings_command or the main WM_COMMAND, so the
   values must be unique here. (A second "180" once sent the search button to
   the shelf.) Panels with their own procedure number their children apart:
   search bar 200+, shelf 190+, style fields 1800+, dictionary 810+. */
enum { IDC_SHELL_TOC = 160, IDC_SHELL_SETTINGS, IDC_SHELL_SEARCH,
       IDC_SHELL_LIGHT = 164, IDC_SHELL_DARK, IDC_SHELL_SYSTEM,
       IDC_SHELL_BACK = 180, IDC_SHELL_TAP20, IDC_SHELL_TAP25, IDC_SHELL_DICTIONARY, IDC_SHELL_SYNC };
static HWND shell_back;
static char *shell_synced_title;
/* The 32px visual has 4px per side for the offset keyboard outline. */
enum { SHELL_BUTTON_BOX = SHELL_ICON_SIZE + 2 * SHELL_CONTROL_FRAME };

static HWND shell_toc, shell_settings;
static HWND shell_search_button;
static void shell_search_create(HWND parent);
static void shell_search_layout(void);
static void shell_search_set(int open);
static void shell_search_reset_book(void);
static int shell_search_key(const MSG *message);
static HWND shell_panel, shell_minus, shell_plus, shell_segments[3];
static int shell_panel_open, shell_animating;
static double shell_animation_start, shell_animation_elapsed;
static float shell_animation_from, shell_animation_value;
static void shell_panel_layout(void);
static void shell_apply_theme(void);
static void shell_toggle_settings(void);
static int shell_settings_command(int id);
static void sy_open(void);
static int shell_draw_settings(const DRAWITEMSTRUCT *item);
static void shell_toc_create(HWND parent);
static void shell_toc_layout(void);
static void shell_toc_load(void);
static void shell_toc_update_current(void);
static void shell_toc_set(int open,int keyboard);
static void shell_toc_hide(void);
static int shell_toc_keyboard;
static int shell_toc_key(HWND focus,WPARAM key,int shift);
static int shell_tab_next(HWND focus,int shift);
static void shell_a11y_names(void);
static int shell_toc_draw(const DRAWITEMSTRUCT *item);
static int shell_toc_open;
static int shell_toc_close_pending;
static HWND shell_toc_test_focus;
static int shell_toc_test_shift;
static HWND shell_toc_panel,shell_toc_list;
static const shell_theme *shell_colors = &shell_theme_light;
static WNDPROC shell_button_base;
static HWND shell_render_focus; /* offscreen drive: inject only the drawing state */
static HWND shell_hover;       /* the button under the mouse */
static int shell_hover_pinned; /* --drive only: keep the hover state for a screenshot */

/* Owner-draw state for shell_d2d_control. The ring follows the keyboard: it is
   hidden while the window hides focus cues. */
static unsigned shell_item_state(const DRAWITEMSTRUCT *item) {
  unsigned state = 0;
  if (shell_hover == item->hwndItem) state |= SHELL_STATE_HOVER;
  if (item->itemState & ODS_SELECTED) state |= SHELL_STATE_PRESSED;
  if ((item->itemState & ODS_FOCUS) && !(item->itemState & ODS_NOFOCUSRECT)) state |= SHELL_STATE_FOCUS;
  if (host_offscreen && g.drive_mode && shell_render_focus == item->hwndItem &&
      !(SendMessageW(item->hwndItem, WM_QUERYUISTATE, 0, 0) & UISF_HIDEFOCUS)) state |= SHELL_STATE_FOCUS;
  if (item->itemState & ODS_DISABLED) state |= SHELL_STATE_DISABLED;
  return state;
}

/* One text button on a surface of colour `under`. */
static void shell_draw_control(const DRAWITEMSTRUCT *item, const wchar_t *text, int kind, uint32_t under) {
  shell_d2d_look look = {kind, shell_item_state(item), under, 0, 1};
  shell_d2d_control(host_shell, item->hDC, &item->rcItem, text, shell_is_dark(), &look);
}

/* The UI face as a GDI font, for native EDIT/STATIC children and GDI-drawn
   lists. One font per size and weight, rebuilt when the DPI changes; callers
   set it again from their layout, which runs on every DPI change. */
static HFONT shell_gdi_font(int size, int weight) {
  static struct { int size, weight; unsigned dpi; HFONT font; } cache[12];
  int slot = -1;
  for (int i = 0; i < 12; i++) {
    if (cache[i].font && cache[i].size == size && cache[i].weight == weight) {
      if (cache[i].dpi == shell_dpi) return cache[i].font;
      slot = i; break;
    }
    if (!cache[i].font && slot < 0) slot = i;
  }
  if (slot < 0) slot = 0;
  HFONT font = CreateFontW(-shell_px((float)size, shell_dpi), 0, 0, 0, weight, 0, 0, 0, DEFAULT_CHARSET, 0, 0,
                           CLEARTYPE_QUALITY, 0, host_shell ? shell_d2d_family(host_shell, SHELL_TEXT_UI) : SHELL_UI_FONTS[2]);
  if (!font) return (HFONT)GetStockObject(DEFAULT_GUI_FONT);
  if (cache[slot].font) DeleteObject(cache[slot].font);
  cache[slot].size = size; cache[slot].weight = weight; cache[slot].dpi = shell_dpi; cache[slot].font = font;
  return font;
}

/* Line height of a GDI font: a single-line EDIT this tall centres its text. */
static int shell_gdi_line(HFONT font) {
  TEXTMETRICW metrics = {0};
  HDC dc = GetDC(NULL);
  HGDIOBJ old = SelectObject(dc, font);
  GetTextMetricsW(dc, &metrics);
  SelectObject(dc, old);
  ReleaseDC(NULL, dc);
  return metrics.tmHeight > 0 ? metrics.tmHeight : shell_px(18, shell_dpi);
}

/* Keep the first requested page-head anchor through resize and font changes.
   Navigation outside that content range starts a new anchor. */
static exr_anchor shell_anchor;
static int shell_anchor_valid;
static int64_t shell_anchor_book;
static size_t shell_anchor_offset, shell_anchor_part;

static void shell_request_layout(void) {
  shell_geometry target = shell_snapshot();
  if (shell_dpi_changing || IsIconic(g.window) || !g.window) return;
  if (shell_wants_reading() && !target.enabled) return;
  if (shell_geometry_equal(target, shell_target)) return;
  if (!shell_anchor_valid && g.frame.valid && !g.frame.fixed) {
    exr_error error = {0};
    shell_anchor_book = g.frame.book_id; shell_anchor_offset = g.frame.range_start; shell_anchor_part = g.frame.part;
    if (g.frame.shell_line_count) shell_anchor_offset = g.frame.shell_lines[0].start;
    if (g.session.txt) shell_anchor_valid = 1;
    else if (g.session.bounded) shell_anchor_valid = host_anchor_copy(&shell_anchor, &g.frame.point);
    else shell_anchor_valid = exr_anchor_create(g.session.document, shell_anchor_offset, shell_anchor_offset,
                                                &shell_anchor, &error) == EXR_OK;
    if (!shell_anchor_valid) { set_status(L"无法建立重排内容锚点。"); return; }
  }
  shell_target = target; shell_epoch++;
  if (g.frame.valid && shell_geometry_equal(g.session.shell_geometry, target)) g.frame.shell_epoch = shell_epoch;
  page_cache_clear();
  shell_layout_waiting = 1;
  SetTimer(g.window, 0x5752, SHELL_REFLOW_MS, NULL);
}

static void shell_pump_layout(void) {
  host_job *job;
  if (shell_failed_epoch == shell_epoch || shell_layout_waiting || g.job || g.pending || g.closing || !g.frame.valid || !g.session.active || IsIconic(g.window)) return;
  if (shell_geometry_equal(g.session.shell_geometry, shell_target)) return;
  if (shell_target.enabled && (shell_target.width <= 0 || shell_target.height <= 0)) return;
  job = job_new(JOB_LAYOUT);
  if (!job) { set_status(L"内存不足，无法重排。"); return; }
  job->book_id = g.session.book_id;
  job->font_percent = g.font_percent;
  if (shell_anchor_valid && shell_anchor_book == g.frame.book_id && shell_anchor_part == g.frame.part) {
    if (!g.session.txt && !host_anchor_copy(&job->anchor, &shell_anchor)) { job_release(job); return; }
    job->has_anchor = !g.session.txt;
    job->target_offset = shell_anchor_offset;
#if defined(EXR_READER_WINDOWS_TXT_PROGRESS) || defined(EXR_READER_WINDOWS_SHELL)
    job->txt_offset = (uint64_t)shell_anchor_offset;
#endif
  }
  job_submit(job);
}

static void shell_adjust_client(RECT *rect, HWND window, unsigned dpi) {
  typedef BOOL (WINAPI *adjust_fn)(LPRECT, DWORD, BOOL, DWORD, UINT);
  adjust_fn adjust = (adjust_fn)(void (*)(void))GetProcAddress(GetModuleHandleW(L"user32.dll"), "AdjustWindowRectExForDpi");
  DWORD style = (DWORD)GetWindowLongPtrW(window, GWL_STYLE), ex = (DWORD)GetWindowLongPtrW(window, GWL_EXSTYLE);
  if (adjust) adjust(rect, style, FALSE, ex, dpi);
  else AdjustWindowRectEx(rect, style, FALSE, ex);
}

static void shell_update_dpi(HWND window) {
  typedef UINT (WINAPI *get_dpi_fn)(HWND);
  typedef HANDLE (WINAPI *get_context_fn)(HWND);
  typedef BOOL (WINAPI *equal_context_fn)(HANDLE, HANDLE);
  HMODULE user = GetModuleHandleW(L"user32.dll");
  get_dpi_fn dpi = (get_dpi_fn)(void (*)(void))GetProcAddress(user, "GetDpiForWindow");
  get_context_fn context = (get_context_fn)(void (*)(void))GetProcAddress(user, "GetWindowDpiAwarenessContext");
  equal_context_fn equal = (equal_context_fn)(void (*)(void))GetProcAddress(user, "AreDpiAwarenessContextsEqual");
  shell_dpi = dpi ? dpi(window) : 96;
  if (!shell_dpi) shell_dpi = 96;
  shell_pmv2 = context && equal && equal(context(window), (HANDLE)(INT_PTR)-4);
  if (host_shell) shell_d2d_set_dpi(host_shell, shell_dpi);
}

/* WM_MOUSEMOVE / WM_MOUSELEAVE of any shell button: one hovered button at a time. */
static void shell_track_hover(HWND window, UINT message) {
  if (message == WM_MOUSEMOVE && shell_hover != window) {
    TRACKMOUSEEVENT track = {sizeof(track), TME_LEAVE, window, 0};
    HWND previous = shell_hover;
    shell_hover = window;
    TrackMouseEvent(&track);
    if (previous) InvalidateRect(previous, NULL, FALSE);
    InvalidateRect(window, NULL, FALSE);
  } else if (message == WM_MOUSELEAVE && shell_hover == window && !shell_hover_pinned) {
    shell_hover = NULL;
    InvalidateRect(window, NULL, FALSE);
  }
}

/* The three right-hand bar buttons sit 6 apart, yet each needs 4 around it
   for its focus ring, so neighbouring windows overlap by 2. Only the focused
   button keeps that strip; the others give it up, or their background would
   cut the ring. Released strips are painted by the bar itself. */
static void shell_bar_regions(HWND focused) {
  HWND buttons[3] = {shell_search_button, shell_toc, shell_settings};
  int overlap = 2 * shell_px(SHELL_CONTROL_FRAME, shell_dpi) - shell_px(SHELL_ICON_GAP, shell_dpi);
  RECT bar;
  if (overlap <= 0 || !g.window) return;
  for (int i = 0; i < 3; i++) if (buttons[i]) {
    RECT box; int trim = buttons[i] == focused ? 0 : overlap;
    GetClientRect(buttons[i], &box);
    SetWindowRgn(buttons[i], CreateRectRgn(trim, 0, box.right - trim, box.bottom), TRUE);
  }
  GetClientRect(g.window, &bar);
  bar.bottom = shell_px(SHELL_TOPBAR_H, shell_dpi);
  InvalidateRect(g.window, &bar, FALSE);
}

static LRESULT CALLBACK shell_button_procedure(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
  switch (message) {
    case WM_SETFOCUS: case WM_KILLFOCUS:
      if (window == shell_toc || window == shell_settings || window == shell_search_button)
        shell_bar_regions(message == WM_SETFOCUS ? window : NULL);
      break;
    case WM_LBUTTONDOWN: if(window==shell_toc) shell_toc_keyboard=0;break;
    case WM_KEYDOWN: if(window==shell_toc) shell_toc_keyboard=1;break;
    case WM_MOUSEMOVE: case WM_MOUSELEAVE:
      shell_track_hover(window, message);
      break;
    case WM_ERASEBKGND:
      return 1;
  }
  return CallWindowProcW(shell_button_base, window, message, wparam, lparam);
}

static HWND shell_make_button(HWND parent, int id, const wchar_t *name) {
  /* Shown only while reading. */
  HWND button = CreateWindowExW(0, L"BUTTON", name, WS_CHILD | WS_TABSTOP | BS_OWNERDRAW, 0, 0, SHELL_BUTTON_BOX,
                                SHELL_BUTTON_BOX, parent, (HMENU)(INT_PTR)id, NULL, NULL);
  if (button) shell_button_base = (WNDPROC)SetWindowLongPtrW(button, GWLP_WNDPROC, (LONG_PTR)shell_button_procedure);
  return button;
}

/* Gives a BUTTON created elsewhere the shell's hover tracking. */
static void shell_adopt_button(HWND button) {
  if (button) shell_button_base = (WNDPROC)SetWindowLongPtrW(button, GWLP_WNDPROC, (LONG_PTR)shell_button_procedure);
}

/* A native check box, so its role and toggle state stay with its UIA proxy,
   painted as a ghost toggle on the bar. The control also draws itself outside
   WM_PAINT (clicks, keys, focus changes): redraw is held off around those
   messages and done here afterwards. */
static struct { HWND window; int held; } shell_toggles[4];
static void shell_toggle_paint(HWND window, HDC dc) {
  RECT box; wchar_t text[32]; unsigned state = 0;
  GetClientRect(window, &box); GetWindowTextW(window, text, 32);
  if (shell_hover == window) state |= SHELL_STATE_HOVER;
  if (CallWindowProcW(shell_button_base, window, BM_GETSTATE, 0, 0) & BST_PUSHED) state |= SHELL_STATE_PRESSED;
  if (GetFocus() == window && !(SendMessageW(window, WM_QUERYUISTATE, 0, 0) & UISF_HIDEFOCUS)) state |= SHELL_STATE_FOCUS;
  if (!IsWindowEnabled(window)) state |= SHELL_STATE_DISABLED;
  if (CallWindowProcW(shell_button_base, window, BM_GETCHECK, 0, 0) == BST_CHECKED) state |= SHELL_STATE_SELECTED;
  shell_d2d_look look = {SHELL_CONTROL_GHOST, state, shell_colors->layer_side, 0, 1};
  if (host_shell) shell_d2d_control(host_shell, dc, &box, text, shell_is_dark(), &look);
}
static LRESULT CALLBACK shell_toggle_procedure(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
  int slot = 0;
  LRESULT result;
  switch (message) {
    case WM_ERASEBKGND: return 1;
    case WM_PAINT: { PAINTSTRUCT paint; shell_toggle_paint(window, BeginPaint(window, &paint)); EndPaint(window, &paint); return 0; }
    case WM_PRINTCLIENT: shell_toggle_paint(window, (HDC)wparam); return 0;
    case WM_MOUSELEAVE: shell_track_hover(window, message); break;
    case WM_MOUSEMOVE:
      shell_track_hover(window, message);
      if (GetCapture() != window) break;
      /* fall through: a captured drag changes the pushed state */
    case WM_LBUTTONDOWN: case WM_LBUTTONUP: case WM_LBUTTONDBLCLK: case WM_KEYDOWN: case WM_KEYUP:
    case WM_SETFOCUS: case WM_KILLFOCUS: case WM_ENABLE: case WM_SETTEXT: case WM_UPDATEUISTATE:
    case WM_CAPTURECHANGED: case BM_SETCHECK: case BM_SETSTATE: case BM_CLICK:
      while (slot < 3 && shell_toggles[slot].window != window) slot++;
      if (!shell_toggles[slot].held++) CallWindowProcW(shell_button_base, window, WM_SETREDRAW, FALSE, 0);
      result = CallWindowProcW(shell_button_base, window, message, wparam, lparam);
      if (!--shell_toggles[slot].held) {
        CallWindowProcW(shell_button_base, window, WM_SETREDRAW, TRUE, 0);
        RedrawWindow(window, NULL, NULL, RDW_INVALIDATE | RDW_UPDATENOW);
      }
      return result;
  }
  return CallWindowProcW(shell_button_base, window, message, wparam, lparam);
}
static void shell_adopt_toggle(HWND button) {
  for (int i = 0; button && i < 4; i++) if (!shell_toggles[i].window) {
    shell_toggles[i].window = button;
    SetWindowLongPtrW(button, GWLP_WNDPROC, (LONG_PTR)shell_toggle_procedure);
    return;
  }
}

static void shell_create_panel(HWND parent);
static void shell_create(HWND parent) {
  shelf_create(parent);
  shell_back=shell_make_button(parent,IDC_SHELL_BACK,L"← 书架");
  shell_toc = shell_make_button(parent, IDC_SHELL_TOC, L"目录");
  shell_settings = shell_make_button(parent, IDC_SHELL_SETTINGS, L"设置");
  shell_create_panel(parent);
  shell_toc_create(parent);
  shell_search_create(parent);
  shell_a11y_names();
}

/* P0 visual bounds: 32px, 6px gap, 12px right inset. */
static void shell_button_circle(HWND button, int client_width, RECT *circle) {
  int right = client_width - shell_px(SHELL_BAR_RIGHT, shell_dpi);
  if (button == shell_toc) right -= shell_px(SHELL_ICON_SIZE + SHELL_ICON_GAP, shell_dpi);
  if (button == shell_search_button) right -= shell_px(2*(SHELL_ICON_SIZE + SHELL_ICON_GAP), shell_dpi);
  circle->left = right - shell_px(SHELL_ICON_SIZE, shell_dpi);
  circle->right = right;
  circle->top = shell_px((SHELL_TOPBAR_H-SHELL_ICON_SIZE)/2, shell_dpi);
  circle->bottom = circle->top + shell_px(SHELL_ICON_SIZE, shell_dpi);
}

static int shell_layout(void) {
  RECT area, circle;
  if(shelf_layout()) return 1;
  if (!shell_active) return 0;
  GetClientRect(g.window, &area);
  MoveWindow(shell_back,shell_px(SHELL_BAR_RIGHT-SHELL_CONTROL_FRAME,shell_dpi),shell_px((SHELL_TOPBAR_H-SHELL_CONTROL_H)/2-SHELL_CONTROL_FRAME,shell_dpi),
    shell_px(80+2*SHELL_CONTROL_FRAME,shell_dpi),shell_px(SHELL_CONTROL_H+2*SHELL_CONTROL_FRAME,shell_dpi),TRUE);
  HWND bar_buttons[4]={shell_back,shell_toc,shell_settings,shell_search_button};
  for(int i=0;i<4;i++) ShowWindow(bar_buttons[i],shell_bar_hidden ? SW_HIDE:SW_SHOWNA);
  shell_button_circle(shell_toc, area.right, &circle);
  MoveWindow(shell_toc, circle.left - shell_px(SHELL_CONTROL_FRAME, shell_dpi), circle.top - shell_px(SHELL_CONTROL_FRAME, shell_dpi), shell_px(SHELL_BUTTON_BOX, shell_dpi),
             shell_px(SHELL_BUTTON_BOX, shell_dpi), TRUE);
  shell_button_circle(shell_settings, area.right, &circle);
  MoveWindow(shell_settings, circle.left - shell_px(SHELL_CONTROL_FRAME, shell_dpi), circle.top - shell_px(SHELL_CONTROL_FRAME, shell_dpi), shell_px(SHELL_BUTTON_BOX, shell_dpi),
             shell_px(SHELL_BUTTON_BOX, shell_dpi), TRUE);
  shell_button_circle(shell_search_button, area.right, &circle);
  MoveWindow(shell_search_button,circle.left-shell_px(SHELL_CONTROL_FRAME,shell_dpi),circle.top-shell_px(SHELL_CONTROL_FRAME,shell_dpi),shell_px(SHELL_BUTTON_BOX,shell_dpi),shell_px(SHELL_BUTTON_BOX,shell_dpi),TRUE);
  shell_bar_regions(GetFocus());
  int page_top=shell_px(SHELL_TOPBAR_H+(shell_search_open ? 48:0),shell_dpi);
  MoveWindow(g.page,0,page_top,area.right,area.bottom>page_top ? area.bottom-page_top:0,TRUE);
  shell_search_layout();
  shell_panel_layout();
  shell_toc_layout();
  sm_refresh();
  return 1;
}

static void shell_enter(void) {
  SetWindowLongPtrW(g.window, GWL_STYLE, GetWindowLongPtrW(g.window, GWL_STYLE) | WS_CLIPCHILDREN);
  SetWindowLongPtrW(g.page,GWL_STYLE,GetWindowLongPtrW(g.page,GWL_STYLE)|WS_CLIPSIBLINGS);
  shell_active = 1;
  ShowWindow(g.page,SW_SHOWNA);
  shell_apply_theme();
  shell_layout();
  shell_request_layout();
  ShowWindow(shell_toc, SW_SHOW);
  ShowWindow(shell_settings, SW_SHOW);
  ShowWindow(shell_search_button, SW_SHOW);
  ShowWindow(shell_back, SW_SHOW);
  InvalidateRect(g.window, NULL, FALSE);
  SetFocus(g.page);
}

static void shell_leave(void) {
  dict_close_all();
  tts_stop();
  tts_command(104); /* close speech controls on leaving the book */
  shell_toc_hide();
  shell_search_set(0);
  shell_panel_open=0; shell_animating=0; shell_animation_value=0;
  KillTimer(g.window,0x5753); ShowWindow(shell_panel,SW_HIDE);
  shell_active = 0;
  ShowWindow(g.page,SW_HIDE);
  shell_apply_theme();
  shell_hover = NULL;
  shell_hover_pinned = 0;
  ShowWindow(shell_toc, SW_HIDE);
  ShowWindow(shell_settings, SW_HIDE);
  ShowWindow(shell_search_button, SW_HIDE);
  ShowWindow(shell_back, SW_HIDE);
  SetWindowLongPtrW(g.window, GWL_STYLE, GetWindowLongPtrW(g.window, GWL_STYLE) & ~(LONG_PTR)WS_CLIPCHILDREN);
  SetWindowLongPtrW(g.page,GWL_STYLE,GetWindowLongPtrW(g.page,GWL_STYLE)&~(LONG_PTR)WS_CLIPSIBLINGS);
  sm_refresh();
  layout_controls();
  shell_request_layout();
  InvalidateRect(g.window, NULL, TRUE);
  SetFocus(g.page);
}

static void shell_sync(void) {
  annot_sync();
  shell_search_reset_book();
  if(shell_toc_close_pending && !g.job && !g.pending) {
    shell_toc_close_pending=0;shell_toc_set(0,0);SetFocus(g.page);
    if(host_offscreen) shell_toc_test_focus=g.page;
  }
  if (shell_anchor_valid && (shell_anchor_book != g.frame.book_id || shell_anchor_part != g.frame.part ||
      shell_anchor_offset < g.frame.range_start || shell_anchor_offset >= g.frame.range_end)) {
    exr_anchor_free(&shell_anchor); shell_anchor_valid = 0;
  }
  if (g.frame.valid && !g.frame.fixed && shell_vertical != g.frame.writing_mode) {
    shell_vertical = g.frame.writing_mode;
    shell_request_layout();
  }
  int want = host_shell && g.window &&
             g.has_current && g.frame.valid && !shelf_requested;
  if(want) shelf_show(0);
  if (want && !shell_active) shell_enter();
  else if (!want && shell_active) shell_leave();
  else if (shell_active) {
    int row = shelf_index(g.current.id);
    const char *title = row >= 0 ? sm_title((size_t)row) : g.current.title;
    if (!title) title = "";
    if (!shell_synced_title || strcmp(shell_synced_title, title)) {
      char *copy = malloc(strlen(title) + 1);
      if (copy) strcpy(copy, title);
      free(shell_synced_title); shell_synced_title = copy;
      RECT bar;
      GetClientRect(g.window, &bar);
      bar.bottom = shell_px(SHELL_TOPBAR_H, shell_dpi);
      InvalidateRect(g.window, &bar, FALSE);
    }
    if(shell_panel_open) InvalidateRect(shell_panel,NULL,FALSE);
  }
  if(!want && host_shell) shelf_show(1);
}

static void shell_paint(HWND window) {
  PAINTSTRUCT paint;
  RECT area, circle;
  wchar_t *title = NULL;
  BeginPaint(window, &paint);
  GetClientRect(window, &area);
  if (SUCCEEDED(shell_d2d_begin(host_shell, shell_bar_hidden ? shell_colors->layer_page:shell_colors->layer_side))) {
    if(!shell_bar_hidden) {
    shell_d2d_fill(host_shell, 0, (float)(shell_px(SHELL_TOPBAR_H, shell_dpi) - 1), (float)area.right, 1, shell_blend(shell_colors->layer_side,shell_colors->line_rgb,SHELL_LINE_ALPHA));
    if(g.has_current) {
      int row=shelf_index(g.current.id);
      const char *name=row>=0 ? sm_title((size_t)row):g.current.title;
      if(name)title=host_wide(name,strlen(name));
    }
    /* P0 title inset; retain the existing ellipsis limit before the controls. */
    shell_button_circle(shell_search_button, area.right, &circle);
    int inset=max(shell_px(112,shell_dpi),area.right-circle.left);
    if(title && area.right>2*inset)
      shell_d2d_text(host_shell,SHELL_TEXT_CENTER,title,(float)inset,0,(float)(area.right-2*inset),
        (float)shell_px(SHELL_TOPBAR_H-1,shell_dpi),shell_colors->text);
    }
    if (shell_d2d_end(host_shell) == S_FALSE) InvalidateRect(window, NULL, FALSE);
  }
  free(title);
  EndPaint(window, &paint);
}

/* Five states (UI-SPEC section 7): normal, hover, pressed, focus, disabled. */
static int shell_draw_item(const DRAWITEMSTRUCT *item) {
  shell_d2d_button look;
  int disabled, pressed, hover, focus;
  if(item->hwndItem==shell_back) { shell_draw_control(item,L"← 书架",SHELL_CONTROL_GHOST,shell_colors->layer_side);return 1; }
  if (shell_toc_draw(item)) return 1;
  if (shell_draw_settings(item)) return 1;
  if (!host_shell || (item->hwndItem != shell_toc && item->hwndItem != shell_settings && item->hwndItem != shell_search_button)) return 0;
  disabled = (item->itemState & ODS_DISABLED) != 0;
  pressed = !disabled && (item->itemState & ODS_SELECTED) != 0;
  hover = !disabled && shell_hover == item->hwndItem;
  /* The outline follows the keyboard: hidden while the window hides focus cues. */
  focus = !disabled && (((item->itemState & ODS_FOCUS) && !(item->itemState & ODS_NOFOCUSRECT)) ||
          (host_offscreen && g.drive_mode && shell_render_focus==item->hwndItem &&
           !(SendMessageW(item->hwndItem,WM_QUERYUISTATE,0,0)&UISF_HIDEFOCUS)));
  memset(&look, 0, sizeof(look));
  look.background = shell_colors->layer_side;
  look.has_fill = pressed || hover;
  look.fill = pressed ? shell_colors->surface3 : shell_colors->surface2;
  look.offset_y = 0;
  look.icon = disabled ? shell_blend(shell_colors->layer_side,shell_colors->text_secondary,SHELL_DISABLED_ALPHA) : (hover || pressed) ? shell_colors->text : shell_colors->text_secondary;
  if(item->hwndItem==shell_search_button && shell_search_open) look.icon=shell_colors->accent;
  if(item->hwndItem==shell_toc && shell_toc_open) look.icon=shell_colors->accent;
  look.has_ring = focus;
  look.ring = shell_colors->accent;
  look.diameter = (float)shell_px(SHELL_ICON_SIZE, shell_dpi);
  look.ring_width = (float)shell_px(SHELL_FOCUS_STROKE, shell_dpi);
  shell_d2d_icon_button(host_shell, item->hDC, &item->rcItem, item->hwndItem == shell_toc ? 0xE8FD : item->hwndItem == shell_search_button ? 0xE721 : 0xE713, &look);
  return 1;
}

/* The page accepts reading keys, but only interactive controls get a ring. */
static const wchar_t *shell_toc_current_label(wchar_t *out, size_t capacity);
static int shell_page_footer(HDC dc, const RECT *area) {
  if (shell_active && g.frame.valid) {
    /* The current page is the strong run. A fixed-layout book knows its total;
       a reflowed chapter does not, so it names the chapter it is in instead. */
    wchar_t text[160], chapter[96]; RECT number = *area; unsigned start = 0, length;
    unsigned long long page = (unsigned long long)(g.frame.page + 1);
    number.top = number.bottom - shell_px(SHELL_PAGE_NUMBER_H, shell_dpi);
    if (g.frame.fixed && g.frame.page_count) {
      length = (unsigned)swprintf(text, 160, L"%llu", page);
      swprintf(text + length, 160 - length, L" / %llu", (unsigned long long)g.frame.page_count);
    } else {
      if (shell_toc_current_label(chapter, 96)) start = (unsigned)swprintf(text, 160, L"%ls · ", chapter);
      else start = (unsigned)swprintf(text, 160, L"%llu · ", (unsigned long long)(g.frame.part + 1));
      length = (unsigned)swprintf(text + start, 160 - start, L"%llu", page);
    }
    shell_d2d_dc_text(host_shell, dc, &number, text, start, length, shell_colors->text_secondary, shell_colors->text_disabled);
  }
  return shell_active;
}

static int shell_translate(const MSG *message) {
  if(dict_translate(message)) return 1;
  if(tts_translate(message)) return 1;
  if(message->message==WM_KEYDOWN && (shell_active || shelf_visible)) {
    if(message->wParam=='W' && (GetKeyState(VK_CONTROL)&0x8000)) {shelf_return();return 1;}
    if(message->wParam=='O' && (GetKeyState(VK_CONTROL)&0x8000)) {g.auto_open_imported=1;import_path(NULL,1);return 1;}
    if(message->wParam==VK_ESCAPE && shell_active && !shell_toc_open && !shell_panel_open && !shell_search_open && !select_valid && !g.selection.active && annot_selected<0) {shelf_return();return 1;}
  }
  if(annot_translate(message)) return 1;
  if(shell_search_key(message)) return 1;
  if(shell_toc_open && message->message==WM_MOUSEWHEEL) {
    RECT panel;GetWindowRect(shell_toc_panel,&panel);POINT p={(short)LOWORD(message->lParam),(short)HIWORD(message->lParam)};
    SendMessageW(PtInRect(&panel,p) ? shell_toc_list:g.page,WM_MOUSEWHEEL,message->wParam,message->lParam);return 1;
  }
  if(message->message==WM_KEYDOWN) {
    int shift=GetKeyState(VK_SHIFT)<0 || (host_offscreen && g.drive_mode && shell_toc_test_shift);
    shell_toc_test_shift=0;
    if(shell_toc_key(message->hwnd,message->wParam,shift)) return 1;
  }
  if(shell_toc_open && message->message==WM_LBUTTONDOWN && message->hwnd==g.page) {shell_toc_set(0,0);return 1;}
  if(shell_panel_open && message->message==WM_KEYDOWN && message->wParam==VK_ESCAPE) {
    shell_toggle_settings(); return 1;
  }
  if(shell_panel_open && message->message==WM_LBUTTONDOWN && message->hwnd!=shell_settings &&
     message->hwnd!=shell_panel && !IsChild(shell_panel,message->hwnd)) shell_toggle_settings();
  if(shell_panel_open && IsDialogMessageW(shell_panel,(MSG *)message)) return 1;
  if (message->message != WM_SYSKEYDOWN || !host_shell || !g.window ||
      (message->hwnd != g.window && !IsChild(g.window, message->hwnd)))
    return 0;
  if (message->wParam == VK_LEFT && shell_active) { shelf_return(); return 1; }
  return 0;
}

/* Visible direct children for acceptance telemetry. */
#ifdef EXR_READER_TEST_DRIVERS
static int shell_visible_children(void) {
  int count = 0;
  HWND child;
  for (child = GetWindow(g.window, GW_CHILD); child; child = GetWindow(child, GW_HWNDNEXT))
    count += IsWindowVisible(child) != 0;
  return count;
}
#endif

#ifdef EXR_READER_TEST_DRIVERS
static HWND shell_button_named(const char *name) {
  return !strcmp(name,"minus") ? shell_minus : !strcmp(name,"plus") ? shell_plus :
    !strcmp(name,"shelf") ? shell_back :
    !strcmp(name,"light") ? shell_segments[0] : !strcmp(name,"dark") ? shell_segments[1] :
    !strcmp(name,"system") ? shell_segments[2] :
    !strcmp(name, "search") ? shell_search_button : !strcmp(name, "toc") ? shell_toc : !strcmp(name, "settings") ? shell_settings : NULL;
}
#endif

#include "shell_settings.inc"
#include "shell_toc.inc"

#include "shell_search.inc"

/* Keyboard order of the reading screen (C2): top bar, text, contents, settings,
   then around again. An open search bar belongs to the top bar, an open contents
   list to the contents button and the open settings panel to the settings button.
   Z-order cannot express this: the panels must stay above the page to paint. */
static int shell_tab_stops(HWND *out, int capacity) {
  HWND stops[64];
  int count = 0;
  stops[count++] = shell_back;
  stops[count++] = shell_search_button;
  if (shell_search_open) {
    stops[count++] = shell_search_edit; stops[count++] = shell_search_prev; stops[count++] = shell_search_next;
    stops[count++] = shell_search_case; stops[count++] = shell_search_word; stops[count++] = shell_search_close;
  }
  stops[count++] = g.page;
  stops[count++] = shell_toc;
  if (shell_toc_open) stops[count++] = shell_toc_count ? shell_toc_list : shell_toc_panel;
  stops[count++] = shell_settings;
  int panel_start = count;
  if (shell_panel_open && shell_panel) {
    HWND child;
    for (child = GetWindow(shell_panel, GW_CHILD); child && count < 64; child = GetWindow(child, GW_HWNDNEXT))
      stops[count++] = child;
  }
  int kept = 0;
  for (int i = 0; i < count && kept < capacity; i++) {
    HWND window = stops[i];
    if (!window || !IsWindowVisible(window) || !IsWindowEnabled(window)) continue;
    if (i >= panel_start && !(GetWindowLongPtrW(window, GWL_STYLE) & WS_TABSTOP)) continue;
    out[kept++] = window;
  }
  return kept;
}

static int shell_tab_next(HWND focus, int shift) {
  HWND stops[64], next;
  int count = shell_tab_stops(stops, 64), at = -1;
  for (int i = 0; i < count && at < 0; i++) if (stops[i] == focus || IsChild(stops[i], focus)) at = i;
  if (at < 0) return 0;
  next = stops[(at + (shift ? count - 1 : 1)) % count];
  shell_toc_keyboard = 1;
  SetFocus(next);
  if (host_offscreen) shell_toc_test_focus = next;
  SendMessageW(g.window, WM_CHANGEUISTATE, MAKEWPARAM(UIS_CLEAR, UISF_HIDEFOCUS), 0);
  InvalidateRect(shell_toc_list, NULL, FALSE);
  return 1;
}

/* Every control on the reading screen states what it is. Owner-drawn glyph
   buttons would otherwise be read as "−", "+", "↑", "×". */
static void shell_a11y_names(void) {
  static const wchar_t *const field[8] = {L"字号", L"行距", L"段距", L"上边距", L"右边距", L"下边距", L"左边距", L"字距"};
  host_a11y_describe(shell_back, L"返回书架", L"回到书架，快捷键 Ctrl+W");
  host_a11y_describe(shell_search_button, L"全文搜索", L"在整本书里搜索文字，快捷键 Ctrl+F");
  host_a11y_describe(shell_toc, L"目录", L"打开或关闭目录，用上下键选章节，回车跳转，Esc 关闭");
  host_a11y_describe(shell_settings, L"设置", L"打开阅读设置：字号、行距、边距、主题和点击分区");
  host_a11y_describe(shell_toc_panel, L"目录面板", L"当前书的章节目录");
  host_a11y_describe(shell_toc_list, L"目录列表", L"上下键选择章节，回车跳转到该章");
  host_a11y_describe(shell_panel, L"阅读设置", L"调整阅读排版和主题，Esc 关闭");
  host_a11y_describe(shell_search_bar, L"全文搜索栏", L"输入关键词，回车查找下一处，Shift+回车查找上一处，Esc 关闭");
  host_a11y_describe(shell_search_edit, L"搜索关键词", L"输入要在全文中查找的文字");
  host_a11y_describe(shell_search_prev, L"上一处", L"跳到上一个搜索结果");
  host_a11y_describe(shell_search_next, L"下一处", L"跳到下一个搜索结果");
  host_a11y_describe(shell_search_case, L"区分大小写", L"选中后搜索区分英文大小写");
  host_a11y_describe(shell_search_word, L"全词匹配", L"选中后只匹配完整的词");
  host_a11y_describe(shell_search_close, L"关闭搜索", L"关闭搜索栏并回到正文");
  host_a11y_describe(shell_search_count, L"搜索结果计数", NULL);
  for (int i = 0; i < 8; i++) {
    wchar_t name[48];
    swprintf(name, 48, L"减小%ls", field[i]); host_a11y_describe(style_buttons[2*i], name, L"按一步减小这一项");
    swprintf(name, 48, L"增大%ls", field[i]); host_a11y_describe(style_buttons[2*i+1], name, L"按一步增大这一项");
    host_a11y_describe(style_edits[i], field[i], L"直接输入数值，离开输入框后生效");
  }
  host_a11y_describe(shell_segments[0], L"浅色主题", L"使用浅色界面");
  host_a11y_describe(shell_segments[1], L"深色主题", L"使用深色界面");
  host_a11y_describe(shell_segments[2], L"跟随系统主题", L"界面颜色跟随 Windows 的深浅色设置");
  host_a11y_describe(style_preset, L"排版预设", L"输入名称保存，或从列表选择已有预设");
  host_a11y_describe(style_save, NULL, L"把当前排版保存为预设");
  host_a11y_describe(style_reset, NULL, L"恢复默认排版");
  host_a11y_describe(shell_tap_buttons[0], L"点击分区 20 / 60 / 20", L"左右各 20% 翻页，中间 60% 显示或隐藏工具栏");
  host_a11y_describe(shell_tap_buttons[1], L"点击分区 25 / 50 / 25", L"左右各 25% 翻页，中间 50% 显示或隐藏工具栏");
  host_a11y_describe(GetDlgItem(shell_panel, IDC_SHELL_DICTIONARY), NULL, L"管理词典和生词本");
  host_a11y_describe(GetDlgItem(shell_panel, IDC_SHELL_SYNC), NULL, L"配置 WebDAV 云同步、查看同步状态和离线草稿");
}
