/* SPDX-License-Identifier: MIT */
/* 2a step 2: the reading screen of the Windows shell (EXR_READER_WINDOWS_SHELL).
   Included once by examples/reader.c, after create_controls and before
   layout_controls; it uses the host state `g` from there.

   Once a book is open the window shows the flat top bar (UI-SPEC, 2026-11-05):
   56 high, layer.page with a 6% hairline on its last row, the title on the left
   (17, weight 600) and two 40x40 round icon buttons on the right (目录, 设置).
   Below it the page fills the window with no 3D edge. Every legacy control is
   hidden. Alt+Left returns to the legacy panel, Alt+Right comes back, and
   opening a book comes back too. --drive keeps the legacy layout unless the
   script says shell|on, so phase-a/b/c run exactly as before. Included after
   create_controls, so create_controls calls shell_create through a forward
   declaration.

   The buttons stay real BUTTON windows (BS_OWNERDRAW): their UIA proxies keep
   the name, role and Invoke, while every pixel is drawn here. In this step
   they only take focus and carry a name; clicking does nothing. */
#include "shell_tokens.h"

enum { IDC_SHELL_TOC = 160, IDC_SHELL_SETTINGS, SHELL_HIDDEN_MAX = 128 };
/* A button window is the circle plus room for the focus outline around it. */
enum { SHELL_BUTTON_BOX = SHELL_TARGET + 2 * SHELL_FOCUS_STROKE };

static int shell_drive_on, shell_legacy, shell_active;
static HWND shell_toc, shell_settings;
static HWND shell_hidden[SHELL_HIDDEN_MAX];
static size_t shell_hidden_count;
static const shell_theme *shell_colors = &shell_theme_light;
static WNDPROC shell_button_base;
static HWND shell_hover;       /* the button under the mouse */
static int shell_hover_pinned; /* --drive only: keep the hover state for a screenshot */

static LRESULT CALLBACK shell_button_procedure(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
  switch (message) {
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

static void shell_create(HWND parent) {
  shell_toc = shell_make_button(parent, IDC_SHELL_TOC, L"目录");
  shell_settings = shell_make_button(parent, IDC_SHELL_SETTINGS, L"设置");
}

/* Circle positions from WIREFRAMES section 2: 设置 16 from the right edge,
   目录 8 to its left, both 8 below the top. */
static void shell_button_circle(HWND button, int client_width, RECT *circle) {
  int right = client_width - SHELL_SPACE_2;
  if (button == shell_toc) right -= SHELL_TARGET + SHELL_SPACE_1;
  circle->left = right - SHELL_TARGET;
  circle->right = right;
  circle->top = SHELL_SPACE_1;
  circle->bottom = SHELL_SPACE_1 + SHELL_TARGET;
}

static int shell_layout(void) {
  RECT area, circle;
  if (!shell_active) return 0;
  GetClientRect(g.window, &area);
  shell_button_circle(shell_toc, area.right, &circle);
  MoveWindow(shell_toc, circle.left - SHELL_FOCUS_STROKE, circle.top - SHELL_FOCUS_STROKE, SHELL_BUTTON_BOX,
             SHELL_BUTTON_BOX, TRUE);
  shell_button_circle(shell_settings, area.right, &circle);
  MoveWindow(shell_settings, circle.left - SHELL_FOCUS_STROKE, circle.top - SHELL_FOCUS_STROKE, SHELL_BUTTON_BOX,
             SHELL_BUTTON_BOX, TRUE);
  MoveWindow(g.page, 0, SHELL_TOPBAR_H, area.right, area.bottom > SHELL_TOPBAR_H ? area.bottom - SHELL_TOPBAR_H : 0,
             TRUE);
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
    if (child == g.page || child == shell_toc || child == shell_settings || !IsWindowVisible(child)) continue;
    if (shell_hidden_count == SHELL_HIDDEN_MAX) break;
    shell_hidden[shell_hidden_count++] = child;
  }
  if (child) { shell_hidden_count = 0; return; } /* more controls than slots: stay on the legacy panel */
  for (i = 0; i < shell_hidden_count; i++) ShowWindow(shell_hidden[i], SW_HIDE);
  SetWindowLongPtrW(g.window, GWL_STYLE, GetWindowLongPtrW(g.window, GWL_STYLE) | WS_CLIPCHILDREN);
  shell_page_edge(0);
  shell_active = 1;
  shell_layout();
  ShowWindow(shell_toc, SW_SHOW);
  ShowWindow(shell_settings, SW_SHOW);
  InvalidateRect(g.window, NULL, FALSE);
  SetFocus(g.page);
}

static void shell_leave(void) {
  size_t i;
  shell_active = 0;
  shell_hover = NULL;
  shell_hover_pinned = 0;
  ShowWindow(shell_toc, SW_HIDE);
  ShowWindow(shell_settings, SW_HIDE);
  SetWindowLongPtrW(g.window, GWL_STYLE, GetWindowLongPtrW(g.window, GWL_STYLE) & ~(LONG_PTR)WS_CLIPCHILDREN);
  shell_page_edge(1);
  for (i = 0; i < shell_hidden_count; i++) ShowWindow(shell_hidden[i], SW_SHOW);
  shell_hidden_count = 0;
  layout_controls();
  InvalidateRect(g.window, NULL, TRUE);
  SetFocus(g.page);
}

static void shell_sync(void) {
  int want = host_shell && g.window && (g.drive_mode ? shell_drive_on : 1) && !shell_legacy &&
             g.has_current && g.frame.valid;
  if (want && !shell_active) shell_enter();
  else if (!want && shell_active) shell_leave();
  else if (shell_active) {
    RECT bar;
    GetClientRect(g.window, &bar);
    bar.bottom = SHELL_TOPBAR_H;
    InvalidateRect(g.window, &bar, FALSE); /* the title may have changed */
  }
}

static void shell_paint(HWND window) {
  PAINTSTRUCT paint;
  RECT area, circle;
  wchar_t *title = NULL;
  BeginPaint(window, &paint);
  GetClientRect(window, &area);
  if (SUCCEEDED(shell_d2d_begin(host_shell, shell_colors->layer_page))) {
    shell_d2d_fill(host_shell, 0, (float)(SHELL_TOPBAR_H - 1), (float)area.right, 1, shell_colors->hairline);
    if (g.has_current && g.current.title) title = host_wide(g.current.title, strlen(g.current.title));
    /* Left at 24; it may run up to 16 before the 目录 circle. */
    shell_button_circle(shell_toc, area.right, &circle);
    if (title && circle.left - SHELL_SPACE_2 > SHELL_SPACE_3)
      shell_d2d_text(host_shell, SHELL_TEXT_TITLE, title, (float)SHELL_SPACE_3, 0,
                     (float)(circle.left - SHELL_SPACE_2 - SHELL_SPACE_3), (float)(SHELL_TOPBAR_H - 1),
                     shell_colors->text);
    if (shell_d2d_end(host_shell) == S_FALSE) InvalidateRect(window, NULL, FALSE);
  }
  free(title);
  EndPaint(window, &paint);
}

/* Five states (UI-SPEC section 7): normal, hover, pressed, focus, disabled. */
static int shell_draw_item(const DRAWITEMSTRUCT *item) {
  shell_d2d_button look;
  int disabled, pressed, hover, focus;
  if (!host_shell || (item->hwndItem != shell_toc && item->hwndItem != shell_settings)) return 0;
  disabled = (item->itemState & ODS_DISABLED) != 0;
  pressed = !disabled && (item->itemState & ODS_SELECTED) != 0;
  hover = !disabled && shell_hover == item->hwndItem;
  /* The outline follows the keyboard: hidden while the window hides focus cues. */
  focus = (item->itemState & ODS_FOCUS) && !(item->itemState & ODS_NOFOCUSRECT);
  memset(&look, 0, sizeof(look));
  look.background = shell_colors->layer_page;
  look.has_fill = pressed || hover;
  look.fill = shell_mix(shell_colors->layer_page, shell_colors->accent, pressed ? SHELL_PRESSED_PERCENT : SHELL_HOVER_PERCENT);
  look.icon = disabled ? shell_colors->text_disabled : shell_colors->text;
  look.has_ring = focus;
  look.ring = shell_colors->accent;
  look.diameter = (float)SHELL_TARGET;
  look.ring_width = (float)SHELL_FOCUS_STROKE;
  shell_d2d_icon_button(host_shell, item->hDC, &item->rcItem, item->hwndItem == shell_toc ? 0xE8FD : 0xE713, &look);
  return 1;
}

/* In the reading screen the page shows keyboard focus as a 2 px accent
   outline inside its edge, only while focus cues are shown. */
static int shell_page_focus(HWND page, HDC dc, const RECT *area) {
  HBRUSH brush;
  RECT edge;
  int i;
  if (!shell_active) return 0;
  if (GetFocus() != page || (SendMessageW(page, WM_QUERYUISTATE, 0, 0) & UISF_HIDEFOCUS)) return 1;
  brush = CreateSolidBrush(RGB((shell_colors->accent >> 16) & 0xFF, (shell_colors->accent >> 8) & 0xFF,
                               shell_colors->accent & 0xFF));
  for (i = 0, edge = *area; i < SHELL_FOCUS_STROKE; i++) {
    FrameRect(dc, &edge, brush);
    InflateRect(&edge, -1, -1);
  }
  DeleteObject(brush);
  return 1;
}

static int shell_translate(const MSG *message) {
  if (message->message != WM_SYSKEYDOWN || !host_shell || !g.window ||
      (message->hwnd != g.window && !IsChild(g.window, message->hwnd)))
    return 0;
  if (message->wParam == VK_LEFT && shell_active) { shell_legacy = 1; shell_sync(); return 1; }
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

/* Visible direct children of the main window: on the reading screen exactly
   the page and the two buttons. */
static int shell_visible_children(void) {
  int count = 0;
  HWND child;
  for (child = GetWindow(g.window, GW_CHILD); child; child = GetWindow(child, GW_HWNDNEXT))
    count += IsWindowVisible(child) != 0;
  return count;
}

static HWND shell_button_named(const char *name) {
  return !strcmp(name, "toc") ? shell_toc : !strcmp(name, "settings") ? shell_settings : NULL;
}
