/* SPDX-License-Identifier: MIT */
/* 2a step 2: the reading screen of the Windows shell (EXR_READER_WINDOWS_SHELL).
   Included once by examples/reader.c, after create_controls and before
   layout_controls; it uses the host state `g` from there.

   Once a book is open the window shows the flat top bar (UI-SPEC, 2026-11-05):
   56 high, DeckMark surface with a line-token hairline on its last row, the title on the left
   (15, weight 650) and two 32x32 rounded icon buttons on the right (目录, 设置).
   Below it the page fills the window with no 3D edge. Every legacy control is
   hidden. The back button, Esc without selection, Ctrl+W and Alt+Left return
   to the recent-books shelf. --drive keeps the legacy layout unless the
   script says shell|on, so phase-a/b/c run exactly as before. Included after
   create_controls, so create_controls calls shell_create through a forward
   declaration.

   The buttons stay real BUTTON windows (BS_OWNERDRAW): their UIA proxies keep
   the name, role and Invoke, while every pixel is drawn here. In this step
   settings opens the owner-drawn child panel. */
#include "shell_tokens.h"

enum { IDC_SHELL_TOC = 160, IDC_SHELL_SETTINGS, SHELL_HIDDEN_MAX = 128 };
enum { IDC_SHELL_BACK=180, IDC_SHELL_TAP20, IDC_SHELL_TAP25, IDC_SHELL_DICTIONARY };
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
static int shell_draw_settings(const DRAWITEMSTRUCT *item);
static void shell_toc_create(HWND parent);
static void shell_toc_layout(void);
static void shell_toc_load(void);
static void shell_toc_update_current(void);
static void shell_toc_set(int open,int keyboard);
static void shell_toc_hide(void);
static int shell_toc_keyboard;
static int shell_toc_key(HWND focus,WPARAM key,int shift);
static int shell_toc_draw(const DRAWITEMSTRUCT *item);
static int shell_toc_open;
static int shell_toc_close_pending;
static HWND shell_toc_test_focus;
static int shell_toc_test_shift;
static HWND shell_toc_panel,shell_toc_list;
static HWND shell_hidden[SHELL_HIDDEN_MAX];
static size_t shell_hidden_count;
static const shell_theme *shell_colors = &shell_theme_light;
static WNDPROC shell_button_base;
static HWND shell_render_focus; /* offscreen drive: inject only the drawing state */
static HWND shell_hover;       /* the button under the mouse */
static int shell_hover_pinned; /* --drive only: keep the hover state for a screenshot */

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

static LRESULT CALLBACK shell_button_procedure(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
  switch (message) {
    case WM_LBUTTONDOWN: if(window==shell_toc) shell_toc_keyboard=0;break;
    case WM_KEYDOWN: if(window==shell_toc) shell_toc_keyboard=1;break;
    case WM_MOUSEMOVE:
      if (shell_hover != window) {
        TRACKMOUSEEVENT track;
        HWND previous = shell_hover;
        memset(&track, 0, sizeof(track));
        track.cbSize = sizeof(track);
        track.dwFlags = TME_LEAVE;
        track.hwndTrack = window;
        shell_hover = window;
        TrackMouseEvent(&track);
        if (previous) InvalidateRect(previous, NULL, FALSE);
        InvalidateRect(window, NULL, FALSE);
      }
      break;
    case WM_MOUSELEAVE:
      if (shell_hover == window && !shell_hover_pinned) {
        shell_hover = NULL;
        InvalidateRect(window, NULL, FALSE);
      }
      break;
    case WM_ERASEBKGND:
      return 1;
  }
  return CallWindowProcW(shell_button_base, window, message, wparam, lparam);
}

static HWND shell_make_button(HWND parent, int id, const wchar_t *name) {
  /* Created hidden, so the legacy panel never shows them. */
  HWND button = CreateWindowExW(0, L"BUTTON", name, WS_CHILD | WS_TABSTOP | BS_OWNERDRAW, 0, 0, SHELL_BUTTON_BOX,
                                SHELL_BUTTON_BOX, parent, (HMENU)(INT_PTR)id, NULL, NULL);
  if (button) shell_button_base = (WNDPROC)SetWindowLongPtrW(button, GWLP_WNDPROC, (LONG_PTR)shell_button_procedure);
  return button;
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
  MoveWindow(shell_back,shell_px(12,shell_dpi),shell_px(8,shell_dpi),shell_px(88,shell_dpi),shell_px(40,shell_dpi),TRUE);
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
  int page_top=shell_px(SHELL_TOPBAR_H+(shell_search_open ? 48:0),shell_dpi);
  MoveWindow(g.page,0,page_top,area.right,area.bottom>page_top ? area.bottom-page_top:0,TRUE);
  shell_search_layout();
  shell_panel_layout();
  shell_toc_layout();
  sm_refresh();
  return 1;
}

/* The legacy page has a sunken 3D edge; the reading screen has none. */
static void shell_page_edge(int on) {
  LONG_PTR style = GetWindowLongPtrW(g.page, GWL_EXSTYLE);
  style = on ? (style | WS_EX_CLIENTEDGE) : (style & ~(LONG_PTR)WS_EX_CLIENTEDGE);
  SetWindowLongPtrW(g.page, GWL_EXSTYLE, style);
  SetWindowPos(g.page, NULL, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED);
}

static void shell_enter(void) {
  HWND child;
  size_t i;
  shell_hidden_count = 0;
  for (child = GetWindow(g.window, GW_CHILD); child; child = GetWindow(child, GW_HWNDNEXT)) {
    if (child == g.page || child == shell_back || child == shell_toc || child == shell_settings || child == shell_search_button || !IsWindowVisible(child)) continue;
    if (shell_hidden_count == SHELL_HIDDEN_MAX) break;
    shell_hidden[shell_hidden_count++] = child;
  }
  if (child) { shell_hidden_count = 0; return; } /* more controls than slots: stay on the legacy panel */
  for (i = 0; i < shell_hidden_count; i++) ShowWindow(shell_hidden[i], SW_HIDE);
  SetWindowLongPtrW(g.window, GWL_STYLE, GetWindowLongPtrW(g.window, GWL_STYLE) | WS_CLIPCHILDREN);
  shell_page_edge(0);
  SetWindowLongPtrW(g.page,GWL_STYLE,GetWindowLongPtrW(g.page,GWL_STYLE)|WS_CLIPSIBLINGS);
  shell_active = 1;
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
  size_t i;
  dict_close_all();
  tts_stop();
  tts_command(104); /* close speech controls on leaving the book */
  shell_toc_hide();
  shell_search_set(0);
  shell_panel_open=0; shell_animating=0; shell_animation_value=0;
  KillTimer(g.window,0x5753); ShowWindow(shell_panel,SW_HIDE);
  shell_active = 0;
  shell_apply_theme();
  shell_hover = NULL;
  shell_hover_pinned = 0;
  ShowWindow(shell_toc, SW_HIDE);
  ShowWindow(shell_settings, SW_HIDE);
  ShowWindow(shell_search_button, SW_HIDE);
  ShowWindow(shell_back, SW_HIDE);
  SetWindowLongPtrW(g.window, GWL_STYLE, GetWindowLongPtrW(g.window, GWL_STYLE) & ~(LONG_PTR)WS_CLIPCHILDREN);
  shell_page_edge(1);
  SetWindowLongPtrW(g.page,GWL_STYLE,GetWindowLongPtrW(g.page,GWL_STYLE)&~(LONG_PTR)WS_CLIPSIBLINGS);
  for (i = 0; i < shell_hidden_count; i++) ShowWindow(shell_hidden[i], SW_SHOW);
  shell_hidden_count = 0;
  {
    RECT bounds; MINMAXINFO limits = {0};
    /* The legacy toolbar needs its original minimum, even after a narrow shell. */
    SendMessageW(g.window, WM_GETMINMAXINFO, 0, (LPARAM)&limits);
    GetWindowRect(g.window, &bounds);
    int width = bounds.right - bounds.left, height = bounds.bottom - bounds.top;
    if (width < limits.ptMinTrackSize.x || height < limits.ptMinTrackSize.y)
      SetWindowPos(g.window, NULL, 0, 0,
        width < limits.ptMinTrackSize.x ? limits.ptMinTrackSize.x : width,
        height < limits.ptMinTrackSize.y ? limits.ptMinTrackSize.y : height,
        SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE);
  }
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
  int want = host_shell && g.window && (g.drive_mode ? shell_drive_on : 1) && !shell_legacy &&
             g.has_current && g.frame.valid && !shelf_requested;
  if(want || shell_legacy || (g.drive_mode && !shell_drive_on)) shelf_show(0);
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
  if(!want && host_shell && !shell_legacy && (!g.drive_mode || shell_drive_on)) shelf_show(1);
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
  if(item->hwndItem==shell_back) {
    shell_d2d_control(host_shell,item->hDC,&item->rcItem,L"← 书架",shell_is_dark(),2,
      (item->itemState&ODS_SELECTED ? 2:0)|(item->itemState&ODS_FOCUS ? 4:0));return 1;
  }
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
static int shell_page_footer(HDC dc, const RECT *area) {
  if (shell_active && g.frame.valid) {
    wchar_t text[96]; RECT number = *area;
    number.top = number.bottom - shell_px(SHELL_PAGE_NUMBER_H, shell_dpi);
    swprintf(text, 96, L"%llu · %llu", (unsigned long long)(g.frame.part + 1), (unsigned long long)(g.frame.page + 1));
    shell_d2d_dc_text(host_shell, dc, &number, text, shell_colors->text_secondary, shell_colors->text_disabled);
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
  if (message->wParam == VK_RIGHT && shell_legacy) { shell_legacy = 0; shell_sync(); return 1; }
  return 0;
}

/* Every control in the 17-row map of HOST-AUDIT section A (IDs 101..117) is
   visible, a tab stop and inside the client area. */
static int shell_legacy_reachable(char *missing, size_t capacity) {
  RECT client, box;
  int id, count = 0;
  size_t used = 0;
  GetClientRect(g.window, &client);
  if (capacity) missing[0] = 0;
  for (id = IDC_IMPORT_EDIT; id <= IDC_CANCEL; id++) {
    HWND control = GetDlgItem(g.window, id);
    int ok = control && IsWindowVisible(control) && (GetWindowLongPtrW(control, GWL_STYLE) & WS_TABSTOP);
    if (ok) {
      GetWindowRect(control, &box);
      MapWindowPoints(NULL, g.window, (POINT *)&box, 2);
      ok = box.right > box.left && box.bottom > box.top && box.left >= 0 && box.top >= 0 &&
           box.right <= client.right && box.bottom <= client.bottom;
    }
    if (ok) count++;
    else if (used + 8 < capacity) used += (size_t)snprintf(missing + used, capacity - used, "%s%d", used ? "," : "", id);
  }
  return count;
}

/* Visible direct children of the main window, for legacy driver telemetry. */
static int shell_visible_children(void) {
  int count = 0;
  HWND child;
  for (child = GetWindow(g.window, GW_CHILD); child; child = GetWindow(child, GW_HWNDNEXT))
    count += IsWindowVisible(child) != 0;
  return count;
}

static HWND shell_button_named(const char *name) {
  return !strcmp(name,"minus") ? shell_minus : !strcmp(name,"plus") ? shell_plus :
    !strcmp(name,"shelf") ? shell_back :
    !strcmp(name,"light") ? shell_segments[0] : !strcmp(name,"dark") ? shell_segments[1] :
    !strcmp(name,"system") ? shell_segments[2] :
    !strcmp(name, "search") ? shell_search_button : !strcmp(name, "toc") ? shell_toc : !strcmp(name, "settings") ? shell_settings : NULL;
}

#include "shell_settings.inc"
#include "shell_toc.inc"

#include "shell_search.inc"
